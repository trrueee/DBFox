from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from math import isfinite
from statistics import fmean, median
from typing import Any

from engine.agent.artifact import (
    ArtifactDraft,
    ArtifactRelationDraft,
    ArtifactRelationType,
    ArtifactType,
)
from engine.errors import ToolInputError
from engine.json_codec import loads
from engine.models import AgentArtifactRecord
from engine.sql.result_view.models import ResultPageQuery, ResultSourceRef
from engine.sql.result_view.service import ResultViewService
from engine.tools.builtin.contracts import (
    ChartCreateInput,
    ChartCreateOutput,
    ResultInspectInput,
    ResultInspectOutput,
    ResultProfileInput,
    ResultProfileOutput,
)
from engine.tools.chart_suggestion import build_chart_series, suggest_plotly_chart
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolObservationProjection,
    ToolOutcome,
    ToolPolicy,
    ToolPresentation,
    ToolRecoveryPolicy,
    ToolRunContext,
    ToolSemanticCapability,
    ToolSemanticSpec,
)
from engine.tools.runtime.observation import (
    bounded_tabular_provider_payload,
    safe_observation_facts,
)


MAX_PROFILE_VALUE_CHARS = 256


def _require_query_result(
    context: ToolRunContext,
    artifact_id: str,
) -> AgentArtifactRecord:
    db = context.require_database()
    request = context.require_request()
    artifact = db.get(AgentArtifactRecord, artifact_id)
    if (
        artifact is None
        or str(artifact.session_id) != request.session_id
        or str(artifact.run_id) != request.run_id
        or str(artifact.type) != ArtifactType.RESULT_VIEW.value
    ):
        raise ToolInputError("The Result Artifact is unavailable in the current Run.")
    payload = loads(str(artifact.payload_json or "{}"))
    if not isinstance(payload, dict):
        raise ToolInputError("The Result Artifact payload is invalid.")
    if str(payload.get("evidenceKind") or "query_result") != "query_result":
        raise ToolInputError(
            "Sample-row Artifacts cannot be inspected as analytical query results."
        )
    return artifact


def _resolve_chart_suggestion(
    tool_input: ChartCreateInput,
    *,
    columns: list[str],
    rows: list[dict],
) -> dict:
    suggestion = suggest_plotly_chart(
        {
            "success": True,
            "columns": columns,
            "rows": rows,
            "rowCount": len(rows),
        }
    )
    if tool_input.x is None or tool_input.y is None:
        if tool_input.chart_type != "auto" and suggestion.get("chartable"):
            suggestion["type"] = tool_input.chart_type
            if tool_input.aggregation == "auto":
                suggestion["aggregation"] = (
                    "none" if tool_input.chart_type == "scatter" else "sum"
                )
        if tool_input.aggregation != "auto" and suggestion.get("chartable"):
            suggestion["aggregation"] = tool_input.aggregation
        if tool_input.title is not None and suggestion.get("chartable"):
            suggestion["title"] = tool_input.title
        return suggestion

    missing = [field for field in (tool_input.x, tool_input.y) if field not in columns]
    if missing:
        available = ", ".join(columns[:30])
        raise ToolInputError(
            f"Chart fields are not present in the Result Artifact: {', '.join(missing)}. "
            f"Available columns: {available}."
        )

    chart_type = (
        tool_input.chart_type
        if tool_input.chart_type != "auto"
        else _infer_chart_type(tool_input.x, rows)
    )
    aggregation = (
        tool_input.aggregation
        if tool_input.aggregation != "auto"
        else ("none" if chart_type == "scatter" else "sum")
    )
    series = build_chart_series(
        rows,
        tool_input.x,
        tool_input.y,
        aggregation=aggregation,
    )
    if not series:
        raise ToolInputError(
            f"Column '{tool_input.y}' does not contain chartable numeric values "
            "in the inspected result sample."
        )
    title = tool_input.title or (
        f"{tool_input.y} vs {tool_input.x}"
        if chart_type == "scatter"
        else f"{tool_input.y} by {tool_input.x}"
    )
    return {
        "type": chart_type,
        "chartable": True,
        "x": tool_input.x,
        "y": tool_input.y,
        "title": title,
        "series": series,
        "reason": (
            "Created from the requested analytical intent with result-backed "
            "field validation."
        ),
        "aggregation": aggregation,
        "sample_size": len(rows),
        "x_label": tool_input.x,
        "y_label": tool_input.y,
        "series_label": tool_input.y,
        "data_label": chart_type in {"bar", "pie"} and len(series) <= 24,
        "dimensions": [
            {
                "name": tool_input.x,
                "column": tool_input.x,
                "role": "x",
                "kind": "category",
            }
        ],
        "metrics": [
            {
                "name": tool_input.y,
                "source_column": tool_input.y,
                "expression": (
                    f"SUM({tool_input.y})" if aggregation == "sum" else tool_input.y
                ),
                "aggregation": aggregation,
                "role": "y",
            }
        ],
    }


def _infer_chart_type(x_column: str, rows: list[dict]) -> str:
    values = [row.get(x_column) for row in rows[:50] if row.get(x_column) is not None]
    if values and all(_number(value) is not None for value in values):
        return "scatter"
    if values and all(_temporal(value) is not None for value in values):
        return "line"
    return "bar"


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _temporal(value: object) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if len(candidate) < 8:
        return None
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00")).isoformat()
    except ValueError:
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            return None


def _profile_rows(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    return [
        _profile_column(column, [row.get(column) for row in rows], top_k=top_k)
        for column in columns
    ]


def _profile_column(
    column: str,
    values: list[object],
    *,
    top_k: int,
) -> dict[str, Any]:
    present = [value for value in values if value is not None]
    numeric = [_number(value) for value in present]
    temporal = [_temporal(value) for value in present]
    if not present:
        kind = "empty"
    elif all(value is not None for value in numeric):
        kind = "number"
    elif all(isinstance(value, bool) for value in present):
        kind = "boolean"
    elif all(value is not None for value in temporal):
        kind = "datetime"
    elif all(isinstance(value, str) for value in present):
        kind = "string"
    else:
        kind = "mixed"

    encoded = [_profile_value(value) for value in present]
    distinct = {value[0] for value in encoded}
    profile: dict[str, Any] = {
        "column": column,
        "kind": kind,
        "sample_count": len(values),
        "non_null_count": len(present),
        "null_count": len(values) - len(present),
        "distinct_count": len(distinct),
    }
    if kind == "number":
        numbers = [value for value in numeric if value is not None]
        profile["numeric"] = {
            "min": min(numbers),
            "max": max(numbers),
            "mean": fmean(numbers),
            "median": median(numbers),
        }
    elif kind == "datetime":
        timestamps = [value for value in temporal if value is not None]
        profile["temporal"] = {
            "min": min(timestamps),
            "max": max(timestamps),
        }

    counts = Counter(key for key, _ in encoded)
    display = {key: value for key, value in encoded}
    profile["top_values"] = [
        {
            "value": display[key],
            "count": count,
            "share": count / len(present),
        }
        for key, count in counts.most_common(top_k)
    ]
    return profile


def _profile_value(value: object) -> tuple[str, str | int | float | bool]:
    number = _number(value)
    if number is not None:
        return f"number:{number}", number
    if isinstance(value, bool):
        return f"boolean:{value}", value
    temporal = _temporal(value)
    if temporal is not None:
        return f"datetime:{temporal}", temporal
    text = str(value)
    display = (
        text
        if len(text) <= MAX_PROFILE_VALUE_CHARS
        else f"{text[:MAX_PROFILE_VALUE_CHARS - 1]}…"
    )
    return f"value:{text}", display


class ResultInspectTool(BaseTool[ResultInspectInput, ResultInspectOutput]):
    name = "result_inspect"
    group = "result"
    description = (
        "Load one transient page from an exact query Result Artifact. Use only when "
        "the needed values are no longer present in the current observation; rows "
        "remain transient and are not copied into Agent memory."
    )
    input_model = ResultInspectInput
    output_model = ResultInspectOutput
    presentation = ToolPresentation(title="查看查询结果", category="explore")
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read", "database_read"),
    )
    semantics = ToolSemanticSpec(
        contributes_progress=False,
        publishes_artifact_references=True,
    )

    def run(
        self,
        tool_input: ResultInspectInput,
        context: ToolRunContext,
    ) -> ResultInspectOutput:
        _require_query_result(context, tool_input.result_artifact_id)
        service = ResultViewService(context.require_database())
        source_ref = ResultSourceRef(artifact_id=tool_input.result_artifact_id)
        source = service.load_verified_source(source_ref)
        page = service.page(
            ResultPageQuery(
                source=source_ref,
                page=tool_input.page,
                page_size=tool_input.page_size,
                count_mode="estimate",
            )
        )
        return ResultInspectOutput(
            result_artifact_id=tool_input.result_artifact_id,
            referenced_artifact_ids=[tool_input.result_artifact_id],
            query_fingerprint=source.fingerprint,
            columns=[str(item) for item in page.columns],
            rows=list(page.rows),
            page=page.page,
            page_size=page.page_size,
            row_count=page.row_count,
            returned_rows=len(page.rows),
            has_next_page=page.has_next_page,
            latency_ms=page.latency_ms,
            warnings=[str(item) for item in page.warnings or []],
            notices=[str(item) for item in page.notices or []],
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="查询结果分页读取失败。")
        columns = [str(item) for item in output.get("columns") or []]
        returned_rows = int(output.get("returned_rows") or 0)
        durable_facts = safe_observation_facts(
            {
                "result_artifact_id": output.get("result_artifact_id"),
                "referenced_artifact_ids": output.get("referenced_artifact_ids") or [],
                "query_fingerprint": output.get("query_fingerprint"),
                "columns": columns,
                "row_count": output.get("row_count"),
                "page": output.get("page"),
                "page_size": output.get("page_size"),
                "returned_rows": returned_rows,
                "has_next_page": output.get("has_next_page"),
                "warnings": output.get("warnings") or [],
                "notices": output.get("notices") or [],
                "recovery": (
                    "Call result_inspect again with this result_artifact_id and "
                    "an explicit page when more values are needed."
                ),
            }
        )
        return ToolObservationProjection(
            summary=(
                f"已读取结果第 {int(output.get('page') or 1)} 页，"
                f"返回 {int(output.get('returned_rows') or 0)} 行。"
            ),
            facts=durable_facts,
            provider_payload=bounded_tabular_provider_payload(
                facts=durable_facts,
                columns=columns,
                rows=list(output.get("rows") or []),
                total_returned_rows=returned_rows,
                source_truncated=bool(output.get("has_next_page")),
            ),
        )


class ResultProfileTool(BaseTool[ResultProfileInput, ResultProfileOutput]):
    name = "result_profile"
    group = "result"
    description = (
        "Profile nulls, distinct values, ranges, central tendency, and frequent "
        "values for selected columns in an exact query Result Artifact. Use this "
        "bounded diagnostic when distribution or data quality matters; use focused "
        "SQL instead when the question requires full-dataset aggregates."
    )
    input_model = ResultProfileInput
    output_model = ResultProfileOutput
    presentation = ToolPresentation(title="分析结果分布与质量", category="query")
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read", "database_read"),
    )
    semantics = ToolSemanticSpec(
        produces=(ToolSemanticCapability.RESULT_PROFILE,),
        publishes_artifact_references=True,
    )

    def run(
        self,
        tool_input: ResultProfileInput,
        context: ToolRunContext,
    ) -> ResultProfileOutput:
        _require_query_result(context, tool_input.result_artifact_id)
        source_ref = ResultSourceRef(artifact_id=tool_input.result_artifact_id)
        service = ResultViewService(context.require_database())
        source = service.load_verified_source(source_ref)
        available = source.column_names
        columns = list(tool_input.columns) or available[:12]
        missing = [column for column in columns if column not in available]
        if missing:
            raise ToolInputError(
                "Profile columns are not present in the Result Artifact: "
                f"{', '.join(missing)}. Available columns: {', '.join(available[:30])}."
            )
        page = service.page(
            ResultPageQuery(
                source=source_ref,
                page=1,
                page_size=tool_input.sample_size,
                count_mode="none",
            )
        )
        warnings = [str(item) for item in page.warnings or []]
        if page.has_next_page:
            warnings.append(
                "Profile is based on a bounded first-page sample, not the full result."
            )
        return ResultProfileOutput(
            result_artifact_id=tool_input.result_artifact_id,
            referenced_artifact_ids=[tool_input.result_artifact_id],
            query_fingerprint=source.fingerprint,
            profiled_columns=columns,
            profiles=_profile_rows(
                list(page.rows),
                columns,
                top_k=tool_input.top_k,
            ),
            sample_size=len(page.rows),
            sample_truncated=page.has_next_page,
            warnings=warnings,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="结果分布与质量分析失败。")
        columns = list(output.get("profiled_columns") or [])
        return ToolObservationProjection(
            summary=(
                f"已分析 {len(columns)} 个结果字段的分布与数据质量，"
                f"样本 {int(output.get('sample_size') or 0)} 行。"
            ),
            facts=safe_observation_facts(
                {
                    "result_artifact_id": output.get("result_artifact_id"),
                    "referenced_artifact_ids": output.get("referenced_artifact_ids")
                    or [],
                    "query_fingerprint": output.get("query_fingerprint"),
                    "profiled_columns": columns,
                    "profiles": output.get("profiles") or [],
                    "sample_size": output.get("sample_size"),
                    "sample_truncated": output.get("sample_truncated"),
                    "warnings": output.get("warnings") or [],
                }
            ),
        )


class ChartCreateTool(BaseTool[ChartCreateInput, ChartCreateOutput]):
    name = "chart_create"
    group = "result"
    description = (
        "Create a verified chart from one exact query Result Artifact. You may "
        "provide a bounded analytical intent and explicit chart fields, or leave "
        "them on auto. The runtime validates fields and numeric values, never uses "
        "a latest result, and never executes model-authored chart code."
    )
    input_model = ChartCreateInput
    output_model = ChartCreateOutput
    presentation = ToolPresentation(title="生成结果图表", category="visualize")
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read", "database_read"),
    )
    semantics = ToolSemanticSpec(publishes_artifact_references=True)

    def run(
        self,
        tool_input: ChartCreateInput,
        context: ToolRunContext,
    ) -> ToolOutcome[ChartCreateOutput]:
        _require_query_result(context, tool_input.result_artifact_id)
        service = ResultViewService(context.require_database())
        source = service.load_verified_source(
            ResultSourceRef(artifact_id=tool_input.result_artifact_id)
        )
        page = service.page(
            ResultPageQuery(
                source=ResultSourceRef(artifact_id=tool_input.result_artifact_id),
                page=1,
                page_size=500,
                count_mode="none",
            )
        )
        suggestion = _resolve_chart_suggestion(
            tool_input,
            columns=[str(column) for column in page.columns],
            rows=list(page.rows),
        )
        output = ChartCreateOutput(
            result_artifact_id=tool_input.result_artifact_id,
            chartable=bool(suggestion.get("chartable")),
            chart_type=str(suggestion.get("type") or "none"),
            x=(str(suggestion["x"]) if suggestion.get("x") is not None else None),
            y=(str(suggestion["y"]) if suggestion.get("y") is not None else None),
            title=(
                str(suggestion["title"])
                if suggestion.get("title") is not None
                else None
            ),
            reason=str(suggestion.get("reason") or ""),
            aggregation=(
                str(suggestion["aggregation"])
                if suggestion.get("aggregation") is not None
                else None
            ),
            sample_size=(
                int(suggestion["sample_size"])
                if suggestion.get("sample_size") is not None
                else None
            ),
            sample_truncated=page.has_next_page,
            query_fingerprint=source.fingerprint,
            intent=tool_input.intent,
            x_label=(
                str(suggestion["x_label"])
                if suggestion.get("x_label") is not None
                else None
            ),
            y_label=(
                str(suggestion["y_label"])
                if suggestion.get("y_label") is not None
                else None
            ),
            series_label=(
                str(suggestion["series_label"])
                if suggestion.get("series_label") is not None
                else None
            ),
            data_label=(
                bool(suggestion["data_label"])
                if suggestion.get("data_label") is not None
                else None
            ),
            dimensions=list(suggestion.get("dimensions") or []),
            metrics=list(suggestion.get("metrics") or []),
        )
        artifacts: tuple[ArtifactDraft, ...] = ()
        if output.chartable:
            artifacts = (
                ArtifactDraft(
                    key="chart",
                    type=ArtifactType.CHART,
                    title=output.title or "数据图表",
                    summary=output.reason,
                    payload={
                        "sourceResultArtifactId": tool_input.result_artifact_id,
                        "chartType": output.chart_type,
                        "x": output.x,
                        "y": [output.y] if output.y else [],
                        "aggregation": output.aggregation,
                        "title": output.title,
                        "intent": output.intent,
                        "queryFingerprint": output.query_fingerprint,
                        "sampleSize": output.sample_size,
                        "sampleTruncated": output.sample_truncated,
                    },
                    relations=(
                        ArtifactRelationDraft(
                            relation=ArtifactRelationType.DERIVED_FROM,
                            artifact_id=tool_input.result_artifact_id,
                        ),
                    ),
                    select_if_none=True,
                ),
            )
        return ToolOutcome(output=output, artifacts=artifacts)

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="图表生成失败。")
        chart = next(
            (
                artifact
                for artifact in artifacts
                if str(getattr(artifact, "type", "")) == "chart"
            ),
            None,
        )
        chart_id = str(getattr(chart, "id", "") or "") or None
        return ToolObservationProjection(
            summary=(
                "图表已生成。"
                if chart_id
                else str(output.get("reason") or "当前结果不适合图表。")
            ),
            facts=safe_observation_facts(
                {
                    "chartable": bool(output.get("chartable")),
                    "chart_artifact_id": chart_id,
                    "result_artifact_id": output.get("result_artifact_id"),
                    "referenced_artifact_ids": [
                        value
                        for value in (
                            output.get("result_artifact_id"),
                            chart_id,
                        )
                        if value
                    ],
                    "chart_type": output.get("chart_type"),
                    "x": output.get("x"),
                    "y": output.get("y"),
                    "title": output.get("title"),
                    "reason": output.get("reason"),
                }
            ),
        )
