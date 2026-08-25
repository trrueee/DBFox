"""Durable result paging owned by the dbfox.data System DLC."""

from __future__ import annotations

import time
from typing import Any

from dbfox_dlc_api import (
    Artifact,
    ArtifactDraft,
    ArtifactRelationDraft,
    ArtifactRelationType,
    BaseTool,
    ExtensionToolRunContext,
    ToolExecutionSpec,
    ToolResourceRequirement,
    ToolInputError,
    ToolObservationProjection,
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
    ToolOutcome,
)

from .artifact_contracts import CHART_ARTIFACT_TYPE, RESULT_VIEW_ARTIFACT_TYPE
from .result_analysis import profile_rows, resolve_chart_suggestion
from .resource_kind import DATABASE_RESOURCE_KIND
from .sql.row_serializer import serialize_rows
from .store import DataStateStore, StoredResultPage
from .tool_contracts import (
    ChartCreateInput,
    ChartCreateOutput,
    ResultInspectInput,
    ResultInspectOutput,
    ResultProfileInput,
    ResultProfileOutput,
)


def _verified_stored_result(
    artifact_id: str,
    context: ExtensionToolRunContext,
    store: DataStateStore,
    *,
    offset: int,
    limit: int,
    analytical_only: bool,
) -> tuple[Artifact, StoredResultPage]:
    try:
        artifact = context.artifact(artifact_id)
    except RuntimeError as exc:
        raise ToolInputError("The Result Artifact is unavailable in this Run.") from exc
    if artifact.type != RESULT_VIEW_ARTIFACT_TYPE:
        raise ToolInputError("The requested Artifact is not a dbfox.data result.")
    if analytical_only and str(
        artifact.payload.get("evidenceKind") or "query_result"
    ) != "query_result":
        raise ToolInputError(
            "Sample-row Artifacts cannot be used for analytical result operations."
        )
    if not artifact.payload_ref:
        raise ToolInputError("This Result Artifact has no durable result payload.")
    database_refs = tuple(
        ref for ref in artifact.resource_refs if ref.kind == DATABASE_RESOURCE_KIND
    )
    if len(database_refs) != 1 or len(artifact.resource_refs) != 1:
        raise ToolInputError("The Result Artifact has an invalid database authority binding.")
    database_ref = database_refs[0]
    if database_ref not in context.scopes(DATABASE_RESOURCE_KIND):
        raise ToolInputError("The Result Artifact database is not authorized in this Run.")
    try:
        stored = store.load_query_result_page(
            artifact.payload_ref,
            offset=offset,
            limit=limit,
        )
    except (KeyError, ValueError, RuntimeError) as exc:
        raise ToolInputError("The durable result payload is unavailable or invalid.") from exc
    if (
        stored.database_resource_id != database_ref.id
        or stored.resource_version != str(database_ref.version or "")
        or stored.query_fingerprint
        != str(artifact.payload.get("queryFingerprint") or "")
    ):
        raise ToolInputError("The Result Artifact does not match its durable payload.")
    return artifact, stored


class ResultInspectTool(BaseTool[ResultInspectInput, ResultInspectOutput]):
    name = "result_inspect"
    group = "result"
    description = (
        "Read one bounded page from the exact durable dbfox.data Result Artifact. "
        "Inspection never reexecutes SQL and cannot cross the frozen database scope."
    )
    input_model = ResultInspectInput
    output_model = ResultInspectOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("filesystem_read",),
        required_resources=(ToolResourceRequirement(kind=DATABASE_RESOURCE_KIND, artifact_selector_field="result_artifact_id"),),
    )
    semantics = ToolSemanticSpec(
        produces=("dbfox.data.query_result",),
        publishes_artifact_references=True,
    )
    presentation = ToolPresentation(title="查看查询结果", category="explore")

    def __init__(self, store: DataStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: ResultInspectInput,
        context: ExtensionToolRunContext,
    ) -> ResultInspectOutput:
        started = time.perf_counter()
        offset = (tool_input.page - 1) * tool_input.page_size
        artifact, stored = _verified_stored_result(
            tool_input.result_artifact_id,
            context,
            self._store,
            offset=offset,
            limit=tool_input.page_size,
            analytical_only=False,
        )

        model_window = serialize_rows(
            stored.rows,
            stored.columns,
            max_columns=50,
            max_cell_chars=2_000,
            max_response_bytes=24_000,
        )
        returned_rows = len(model_window.rows)
        has_next_page = (
            offset + len(stored.rows) < stored.row_count
            or model_window.truncation.response_bytes
        )
        warnings: list[str] = []
        if stored.source_truncated:
            warnings.append(
                "The source query exceeded the Data result-store boundary; only stored rows are inspectable."
            )
        if model_window.truncated:
            warnings.append(
                "This model observation page exceeded its byte or cell boundary; retry with a smaller page_size."
            )
        return ResultInspectOutput(
            result_artifact_id=artifact.id,
            referenced_artifact_ids=[artifact.id],
            query_fingerprint=stored.query_fingerprint,
            columns=model_window.columns,
            rows=model_window.rows,
            page=tool_input.page,
            page_size=tool_input.page_size,
            row_count=stored.row_count,
            returned_rows=returned_rows,
            has_next_page=has_next_page,
            latency_ms=int((time.perf_counter() - started) * 1_000),
            warnings=warnings,
            notices=["Loaded from the durable Data result store without SQL reexecution."],
        )

    def project_observation(self, *, status, output, artifacts):
        del artifacts
        if status != "success":
            return ToolObservationProjection(summary="查询结果分页读取失败。")
        columns = [str(item) for item in output.get("columns") or []]
        returned_rows = int(output.get("returned_rows") or 0)
        facts: dict[str, Any] = {
            "result_artifact_id": output.get("result_artifact_id"),
            "referenced_artifact_ids": output.get("referenced_artifact_ids") or [],
            "query_fingerprint": output.get("query_fingerprint"),
            "columns": columns,
            "row_count": output.get("row_count"),
            "page": output.get("page"),
            "page_size": output.get("page_size"),
            "returned_rows": returned_rows,
            "has_next_page": bool(output.get("has_next_page")),
            "warnings": output.get("warnings") or [],
            "notices": output.get("notices") or [],
        }
        return ToolObservationProjection(
            summary=f"已从耐久结果读取第 {int(output.get('page') or 1)} 页，返回 {returned_rows} 行。",
            facts=facts,
            provider_payload={**facts, "rows": list(output.get("rows") or [])},
        )


class ResultProfileTool(BaseTool[ResultProfileInput, ResultProfileOutput]):
    name = "result_profile"
    group = "result"
    description = (
        "Profile nulls, distinct values, ranges, and frequent values from one "
        "exact durable analytical Result Artifact without reexecuting SQL."
    )
    input_model = ResultProfileInput
    output_model = ResultProfileOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("filesystem_read",),
        required_resources=(ToolResourceRequirement(kind=DATABASE_RESOURCE_KIND, artifact_selector_field="result_artifact_id"),),
    )
    semantics = ToolSemanticSpec(publishes_artifact_references=True)
    presentation = ToolPresentation(title="分析结果分布与质量", category="query")

    def __init__(self, store: DataStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: ResultProfileInput,
        context: ExtensionToolRunContext,
    ) -> ResultProfileOutput:
        artifact, stored = _verified_stored_result(
            tool_input.result_artifact_id,
            context,
            self._store,
            offset=0,
            limit=tool_input.sample_size,
            analytical_only=True,
        )
        columns = list(tool_input.columns) or stored.columns[:12]
        missing = [column for column in columns if column not in stored.columns]
        if missing:
            raise ToolInputError(
                "Profile columns are not present in the Result Artifact: "
                f"{', '.join(missing)}. Available columns: {', '.join(stored.columns[:30])}."
            )
        sample_truncated = (
            stored.source_truncated or stored.row_count > len(stored.rows)
        )
        warnings = (
            ["Profile is based on the bounded durable result sample, not the full source query."]
            if sample_truncated
            else []
        )
        return ResultProfileOutput(
            result_artifact_id=artifact.id,
            referenced_artifact_ids=[artifact.id],
            query_fingerprint=stored.query_fingerprint,
            profiled_columns=columns,
            profiles=profile_rows(stored.rows, columns, top_k=tool_input.top_k),
            sample_size=len(stored.rows),
            sample_truncated=sample_truncated,
            warnings=warnings,
        )

    def project_observation(self, *, status, output, artifacts):
        del artifacts
        if status != "success":
            return ToolObservationProjection(summary="结果分布与质量分析失败。")
        columns = list(output.get("profiled_columns") or [])
        return ToolObservationProjection(
            summary=(
                f"已从耐久结果分析 {len(columns)} 个字段，"
                f"样本 {int(output.get('sample_size') or 0)} 行。"
            ),
            facts={
                "result_artifact_id": output.get("result_artifact_id"),
                "referenced_artifact_ids": output.get("referenced_artifact_ids") or [],
                "query_fingerprint": output.get("query_fingerprint"),
                "profiled_columns": columns,
                "profiles": output.get("profiles") or [],
                "sample_size": output.get("sample_size"),
                "sample_truncated": bool(output.get("sample_truncated")),
                "warnings": output.get("warnings") or [],
            },
        )


class ChartCreateTool(BaseTool[ChartCreateInput, ChartCreateOutput]):
    name = "chart_create"
    group = "result"
    description = (
        "Create a verified chart description from one exact durable analytical "
        "Result Artifact; fields are checked and no model-authored code runs."
    )
    input_model = ChartCreateInput
    output_model = ChartCreateOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("filesystem_read",),
        required_resources=(ToolResourceRequirement(kind=DATABASE_RESOURCE_KIND, artifact_selector_field="result_artifact_id"),),
    )
    semantics = ToolSemanticSpec(publishes_artifact_references=True)
    presentation = ToolPresentation(title="生成结果图表", category="visualize")

    def __init__(self, store: DataStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: ChartCreateInput,
        context: ExtensionToolRunContext,
    ) -> ToolOutcome[ChartCreateOutput]:
        artifact, stored = _verified_stored_result(
            tool_input.result_artifact_id,
            context,
            self._store,
            offset=0,
            limit=500,
            analytical_only=True,
        )
        suggestion = resolve_chart_suggestion(
            tool_input,
            columns=stored.columns,
            rows=stored.rows,
        )
        sample_truncated = (
            stored.source_truncated or stored.row_count > len(stored.rows)
        )
        output = ChartCreateOutput(
            result_artifact_id=artifact.id,
            chartable=bool(suggestion.get("chartable")),
            chart_type=str(suggestion.get("type") or "none"),
            x=str(suggestion["x"]) if suggestion.get("x") is not None else None,
            y=str(suggestion["y"]) if suggestion.get("y") is not None else None,
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
            sample_truncated=sample_truncated,
            query_fingerprint=stored.query_fingerprint,
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
            database_ref = artifact.resource_refs[0]
            artifacts = (
                ArtifactDraft(
                    key="chart",
                    type=CHART_ARTIFACT_TYPE,
                    title=output.title or "数据图表",
                    summary=output.reason,
                    payload={
                        "sourceResultArtifactId": artifact.id,
                        "chartType": output.chart_type,
                        "x": output.x,
                        "y": [output.y] if output.y else [],
                        "aggregation": output.aggregation,
                        "title": output.title,
                    },
                    relations=(
                        ArtifactRelationDraft(
                            relation=ArtifactRelationType.DERIVED_FROM,
                            artifact_id=artifact.id,
                        ),
                    ),
                    resource_refs=(database_ref,),
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
                if str(getattr(artifact, "type", "")) == CHART_ARTIFACT_TYPE
            ),
            None,
        )
        chart_id = str(getattr(chart, "id", "") or "") or None
        return ToolObservationProjection(
            summary=(
                "图表已从耐久结果生成。"
                if chart_id
                else str(output.get("reason") or "当前结果不适合图表。")
            ),
            facts={
                "chartable": bool(output.get("chartable")),
                "chart_artifact_id": chart_id,
                "result_artifact_id": output.get("result_artifact_id"),
                "chart_type": output.get("chart_type"),
                "x": output.get("x"),
                "y": output.get("y"),
                "sample_size": output.get("sample_size"),
                "sample_truncated": bool(output.get("sample_truncated")),
            },
        )
