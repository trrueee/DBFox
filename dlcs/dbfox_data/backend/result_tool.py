"""Durable result paging owned by the dbfox.data System DLC."""

from __future__ import annotations

import time
from typing import Any

from dbfox_dlc_api import (
    Artifact,
    ArtifactRepresentationContext,
    ArtifactRepresentationRequest,
    ArtifactRepresentationResult,
    BaseTool,
    DataFramePage,
    ExtensionToolRunContext,
    ToolExecutionSpec,
    ToolResourceRequirement,
    ToolInputError,
    ToolObservationProjection,
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
)

from .artifact_contracts import (
    RESULT_VIEW_ARTIFACT_TYPE,
    SNAPSHOT_ARTIFACT_TYPE,
)
from .result_analysis import profile_rows
from .result_view import DataRepresentationRows, DataResultRepresentation
from .resource_kind import DATABASE_RESOURCE_KIND
from .sql.row_serializer import serialize_rows
from .tool_contracts import (
    ResultInspectInput,
    ResultInspectOutput,
    ResultProfileInput,
    ResultProfileOutput,
)


def _representation_context(
    context: ExtensionToolRunContext,
) -> ArtifactRepresentationContext:
    def load(artifact_id: str) -> Artifact | None:
        try:
            return context.artifact(artifact_id)
        except RuntimeError:
            return None

    return ArtifactRepresentationContext(artifact_loader=load)


def _verified_result(
    artifact_id: str,
    context: ExtensionToolRunContext,
    representation: DataResultRepresentation,
    *,
    limit: int,
    analytical_only: bool,
) -> tuple[Artifact, DataRepresentationRows]:
    artifact = _verified_artifact(
        artifact_id,
        context,
        analytical_only=analytical_only,
    )
    try:
        rows = representation.rows(
            artifact,
            _representation_context(context),
            max_rows=limit,
        )
    except Exception as exc:
        raise ToolInputError("The Result representation is unavailable or invalid.") from exc
    return artifact, rows


def _verified_artifact(
    artifact_id: str,
    context: ExtensionToolRunContext,
    *,
    analytical_only: bool,
) -> Artifact:
    try:
        artifact = context.artifact(artifact_id)
    except RuntimeError as exc:
        raise ToolInputError("The Result Artifact is unavailable in this Run.") from exc
    if artifact.type not in {RESULT_VIEW_ARTIFACT_TYPE, SNAPSHOT_ARTIFACT_TYPE}:
        raise ToolInputError("The requested Artifact is not a dbfox.data result or snapshot.")
    if analytical_only and str(
        artifact.payload.get("evidenceKind") or "query_result"
    ) != "query_result":
        raise ToolInputError(
            "Sample-row Artifacts cannot be used for analytical result operations."
        )
    database_refs = tuple(
        ref for ref in artifact.resource_refs if ref.kind == DATABASE_RESOURCE_KIND
    )
    if len(database_refs) != 1 or len(artifact.resource_refs) != 1:
        raise ToolInputError("The Result Artifact has an invalid database authority binding.")
    database_ref = database_refs[0]
    if database_ref not in context.scopes(DATABASE_RESOURCE_KIND):
        raise ToolInputError("The Result Artifact database is not authorized in this Run.")
    return artifact


def _rows_from_page(page: DataFramePage) -> list[dict[str, Any]]:
    return [
        {field.name: field.values[index] for field in page.fields}
        for index in range(page.returned_row_count)
    ]


class ResultInspectTool(BaseTool[ResultInspectInput, ResultInspectOutput]):
    name = "result_inspect"
    group = "result"
    description = (
        "Read one bounded page through the dbfox.data DataFrame representation. "
        "Live Results reexecute their immutable SQL source; Snapshots remain exact."
    )
    input_model = ResultInspectInput
    output_model = ResultInspectOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("network", "filesystem_read"),
        required_resources=(ToolResourceRequirement(kind=DATABASE_RESOURCE_KIND, artifact_selector_field="result_artifact_id"),),
    )
    semantics = ToolSemanticSpec(
        produces=("dbfox.data.query_result",),
        publishes_artifact_references=True,
    )
    presentation = ToolPresentation(title="查看查询结果", category="explore")

    def __init__(self, representation: DataResultRepresentation) -> None:
        self._representation = representation

    def run(
        self,
        tool_input: ResultInspectInput,
        context: ExtensionToolRunContext,
    ) -> ResultInspectOutput:
        started = time.perf_counter()
        artifact = _verified_artifact(
            tool_input.result_artifact_id,
            context,
            analytical_only=False,
        )
        try:
            represented = self._representation.execute(
                artifact,
                ArtifactRepresentationRequest(
                    operation="page",
                    parameters={
                        "page": tool_input.page,
                        "page_size": tool_input.page_size,
                        "count_mode": "exact",
                    },
                ),
                _representation_context(context),
            )
            if not isinstance(represented, ArtifactRepresentationResult):
                raise TypeError("DataFrame page returned a stream")
            page = DataFramePage.model_validate(represented.payload)
        except Exception as exc:
            raise ToolInputError("The Result DataFrame page is unavailable.") from exc
        page_rows = _rows_from_page(page)
        model_window = serialize_rows(
            page_rows,
            [field.name for field in page.fields],
            max_columns=50,
            max_cell_chars=2_000,
            max_response_bytes=24_000,
        )
        returned_rows = len(model_window.rows)
        has_next_page = page.has_next_page or model_window.truncation.response_bytes
        warnings = list(represented.warnings)
        if model_window.truncated:
            warnings.append(
                "This model observation page exceeded its byte or cell boundary; retry with a smaller page_size."
            )
        return ResultInspectOutput(
            result_artifact_id=artifact.id,
            referenced_artifact_ids=[artifact.id],
            query_fingerprint=represented.source_fingerprint,
            columns=model_window.columns,
            rows=model_window.rows,
            page=tool_input.page,
            page_size=tool_input.page_size,
            row_count=page.row_count,
            returned_rows=returned_rows,
            has_next_page=has_next_page,
            latency_ms=int((time.perf_counter() - started) * 1_000),
            warnings=warnings,
            notices=list(represented.notices),
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
            summary=f"已读取结果第 {int(output.get('page') or 1)} 页，返回 {returned_rows} 行。",
            facts=facts,
            provider_payload={**facts, "rows": list(output.get("rows") or [])},
        )


class ResultProfileTool(BaseTool[ResultProfileInput, ResultProfileOutput]):
    name = "result_profile"
    group = "result"
    description = (
        "Profile nulls, distinct values, ranges, and frequent values from one "
        "bounded Data Result or explicit Snapshot through its DataFrame provider."
    )
    input_model = ResultProfileInput
    output_model = ResultProfileOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("network", "filesystem_read"),
        required_resources=(ToolResourceRequirement(kind=DATABASE_RESOURCE_KIND, artifact_selector_field="result_artifact_id"),),
    )
    semantics = ToolSemanticSpec(publishes_artifact_references=True)
    presentation = ToolPresentation(title="分析结果分布与质量", category="query")

    def __init__(self, representation: DataResultRepresentation) -> None:
        self._representation = representation

    def run(
        self,
        tool_input: ResultProfileInput,
        context: ExtensionToolRunContext,
    ) -> ResultProfileOutput:
        artifact, represented = _verified_result(
            tool_input.result_artifact_id,
            context,
            self._representation,
            limit=tool_input.sample_size,
            analytical_only=True,
        )
        columns = list(tool_input.columns) or represented.columns[:12]
        missing = [column for column in columns if column not in represented.columns]
        if missing:
            raise ToolInputError(
                "Profile columns are not present in the Result Artifact: "
                f"{', '.join(missing)}. Available columns: {', '.join(represented.columns[:30])}."
            )
        sample_truncated = represented.source_truncated
        warnings = (
            ["Profile is based on a bounded DataFrame sample, not the full source query."]
            if sample_truncated
            else []
        )
        return ResultProfileOutput(
            result_artifact_id=artifact.id,
            referenced_artifact_ids=[artifact.id],
            query_fingerprint=represented.source_fingerprint,
            profiled_columns=columns,
            profiles=profile_rows(represented.rows, columns, top_k=tool_input.top_k),
            sample_size=len(represented.rows),
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
                f"已分析结果中的 {len(columns)} 个字段，"
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
