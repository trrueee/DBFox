from __future__ import annotations

from dlcs.dbfox_data.backend.resource_kind import DATABASE_RESOURCE_KIND

from engine.agent.artifact import (
    ArtifactDraft,
    ArtifactRelationDraft,
    ArtifactRelationType,
    ArtifactType,
)
from engine.agent.repositories.artifact import ArtifactRepository
from engine.errors import ToolInputError
from engine.models import AgentArtifactRecord
from engine.resource import ResourceScopeRef
from engine.sql.result_view.models import ResultPageQuery, ResultSourceRef
from engine.sql.result_view.service import ResultViewService
from dlcs.dbfox_data.backend.tool_contracts import (
    ChartCreateInput,
    ChartCreateOutput,
    ResultInspectInput,
    ResultInspectOutput,
    ResultProfileInput,
    ResultProfileOutput,
)
from dlcs.dbfox_data.backend.result_analysis import (
    profile_rows,
    resolve_chart_suggestion,
)
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


def _require_query_result(
    context: ToolRunContext,
    artifact_id: str,
) -> tuple[AgentArtifactRecord, ResourceScopeRef]:
    db = context.require_metadata()
    request = context.require_request()
    repository = ArtifactRepository(db)
    database_ref = repository.bound_resource_ref(artifact_id, kind=DATABASE_RESOURCE_KIND)
    if database_ref is None or context.scope(DATABASE_RESOURCE_KIND, database_ref.id) != database_ref:
        raise ToolInputError(
            "The Result Artifact database is not authorized for this Run."
        )
    artifact = repository.available_result(
        current_run_id=request.run_id,
        artifact_id=artifact_id,
        session_id=request.session_id,
        resource_ref=database_ref,
    )
    if artifact is None:
        raise ToolInputError(
            "The Result Artifact is unavailable in this datasource session."
        )
    payload = artifact.payload
    if not isinstance(payload, dict):
        raise ToolInputError("The Result Artifact payload is invalid.")
    if str(payload.get("evidenceKind") or "query_result") != "query_result":
        raise ToolInputError(
            "Sample-row Artifacts cannot be inspected as analytical query results."
        )
    record = db.get(AgentArtifactRecord, artifact.id)
    if record is None:
        raise ToolInputError("The Result Artifact is unavailable.")
    return record, database_ref


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
        required_resource_kinds=(DATABASE_RESOURCE_KIND,),
    )
    semantics = ToolSemanticSpec(
        produces=(ToolSemanticCapability.QUERY_RESULT,),
        contributes_progress=False,
        publishes_artifact_references=True,
    )

    def run(
        self,
        tool_input: ResultInspectInput,
        context: ToolRunContext,
    ) -> ResultInspectOutput:
        _require_query_result(context, tool_input.result_artifact_id)
        service = ResultViewService(context.require_metadata())
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
        required_resource_kinds=(DATABASE_RESOURCE_KIND,),
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
        service = ResultViewService(context.require_metadata())
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
            profiles=profile_rows(
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
        required_resource_kinds=(DATABASE_RESOURCE_KIND,),
    )
    semantics = ToolSemanticSpec(publishes_artifact_references=True)

    def run(
        self,
        tool_input: ChartCreateInput,
        context: ToolRunContext,
    ) -> ToolOutcome[ChartCreateOutput]:
        _, database_ref = _require_query_result(
            context,
            tool_input.result_artifact_id,
        )
        service = ResultViewService(context.require_metadata())
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
        suggestion = resolve_chart_suggestion(
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
                    },
                    relations=(
                        ArtifactRelationDraft(
                            relation=ArtifactRelationType.DERIVED_FROM,
                            artifact_id=tool_input.result_artifact_id,
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
                    "sample_size": output.get("sample_size"),
                    "sample_truncated": output.get("sample_truncated"),
                }
            ),
        )
