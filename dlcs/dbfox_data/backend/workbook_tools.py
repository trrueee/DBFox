"""Two bounded workbook Tools; computation continues through existing SQL Tools."""
from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from dbfox_dlc_api import (
    ATTACHMENT_RESOURCE_KIND, ArtifactDraft, ArtifactVisibility, AttachmentResourceHandle,
    BaseTool, ContextFragment, Field, ToolExecutionSpec, ToolInputError, ToolInputModel,
    ToolObservationProjection, ToolOutcome, ToolOutputModel, ToolPolicy, ToolPresentation,
    ToolResourceRequirement, ToolSemanticSpec, json_dumps,
)
from pydantic import JsonValue

from .contracts import WorkbookColumn, WorkbookRegion, WorkbookSource
from .workbook import WorkbookService

WORKBOOK_ARTIFACT_TYPE = "dbfox.data.workbook"


class WorkbookInspectInput(ToolInputModel):
    attachment_id: str = Field(min_length=1, max_length=128)
    sheet: str | None = Field(default=None, min_length=1, max_length=128)
    cell_range: str | None = Field(default=None, min_length=2, max_length=32,
                                   description="Optional A1:H32 window, at most 64 rows and 16 columns. Follow next_range to read later sections/notes.")


class WorkbookInspectOutput(ToolOutputModel):
    workbook: dict[str, JsonValue]


class WorkbookPrepareInput(ToolInputModel):
    attachment_id: str = Field(min_length=1, max_length=128)
    sheet: str = Field(min_length=1, max_length=128)
    header_row: int = Field(ge=1, le=100_001)
    columns: list[Annotated[str, Field(min_length=1, max_length=256)]] | None = Field(default=None, min_length=1, max_length=128)
    column_types: dict[str, Literal["text", "decimal", "integer", "date", "datetime", "boolean"]] = Field(default_factory=dict, max_length=128)
    exclude_rows: dict[int, Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=dict, max_length=100)
    regions: list[WorkbookRegion] | None = Field(default=None, min_length=1, max_length=24,
        description="Explicit non-overlapping detail ranges after header_row, e.g. A4:E13. Each context_cells maps an added text field to an original label cell such as A2; all regions share those field names. Omit for a flat table. Never omit invalid business records by shrinking a region.")


class WorkbookPrepared(ToolOutputModel):
    database_id: str
    resource_version: str
    table: Literal["main.data"] = "main.data"
    row_count: int
    columns: tuple[WorkbookColumn, ...]
    source: WorkbookSource


def _source(context, attachment_id: str) -> AttachmentResourceHandle:
    refs = [r for r in context.scopes(ATTACHMENT_RESOURCE_KIND) if r.id == attachment_id]
    if len(refs) != 1:
        raise ToolInputError("指定附件不在本次工具调用的授权范围内。")
    resource = context.resource(refs[0])
    if not isinstance(resource, AttachmentResourceHandle):
        raise ToolInputError("附件读取能力不可用。")
    return resource


class WorkbookInspectTool(BaseTool[WorkbookInspectInput, WorkbookInspectOutput]):
    name = "workbook_inspect"
    group = "query"
    description = "Inspect exact attachment sheet names, cell coordinates, header candidates and bounded rows. Use cell_range and next_range to inspect later sections, repeated headers, notes and appendices before preparing a structured workbook. Samples never establish totals. Clarify unresolved business ambiguity between plausible sheets/files."
    input_model = WorkbookInspectInput
    output_model = WorkbookInspectOutput
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(backend="isolated_process", timeout_seconds=60, recovery="retry_safe",
                                 capabilities=("filesystem_read",), max_output_bytes=32_768,
                                 required_resources=(ToolResourceRequirement(kind=ATTACHMENT_RESOURCE_KIND, selector_field="attachment_id"),))
    presentation = ToolPresentation(title="读取工作簿结构", category="explore")
    semantics = ToolSemanticSpec(produces=("dbfox.data.workbook_structure",))

    def __init__(self, service: WorkbookService):
        self.service = service

    def run(self, tool_input, context):
        return WorkbookInspectOutput(workbook=self.service.inspect(_source(context, tool_input.attachment_id),
                                                                 sheet=tool_input.sheet, cell_range=tool_input.cell_range,
                                                                 cancelled=context.is_cancelled))

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="工作簿检视未完成。")
        workbook = output.get("workbook", {})
        table = workbook.get("table") or {}
        # Samples stay in the transient provider payload. Only bounded source /
        # structure facts are durable and contribute to the neutral progress guard.
        structure = {"content_sha256": workbook.get("content_sha256"), "sheets": workbook.get("sheets", []),
                     "sheet": table.get("sheet"), "cell_range": table.get("cell_range"),
                     "scanned_through_row": table.get("scanned_through_row"),
                     "header_locations": [{"row": h["row"], "columns": h["columns"]} for h in table.get("candidate_headers", [])]}
        facts = {**structure, "structure_fingerprint": hashlib.sha256(json_dumps(structure).encode()).hexdigest()}
        return ToolObservationProjection(summary="已读取工作簿结构和有界样本；尚未计算统计结果。", facts=facts, provider_payload=output)


class WorkbookPrepareTool(BaseTool[WorkbookPrepareInput, WorkbookPrepared]):
    name = "workbook_prepare"
    group = "query"
    description = "Prepare selected columns and optional explicit detail regions of one exact attachment/sheet into an immutable database. Ignore unselected blank header columns. For sectioned sheets, inspect all relevant sections and notes, select actual detail ranges and optionally copy category labels from context_cells. Titles, repeated headers and subtotals belong outside detail ranges; invalid business records cannot be hidden that way. Missing/invalid numeric values and formulas require clarification or user-authorized exclude_rows. Preserve __source_row and source recipe; report partial scope and distinguish option lists from requirements. Then sql_validate -> sql_execute_readonly; preparation is not an analysis result."
    input_model = WorkbookPrepareInput
    output_model = WorkbookPrepared
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(backend="isolated_process", timeout_seconds=60, recovery="retry_safe",
                                 capabilities=("filesystem_read", "filesystem_write"), max_output_bytes=65_536,
                                 required_resources=(ToolResourceRequirement(kind=ATTACHMENT_RESOURCE_KIND, selector_field="attachment_id"),))
    presentation = ToolPresentation(title="准备工作簿明细", category="query")
    semantics = ToolSemanticSpec(produces=("dbfox.data.dataset",))

    def __init__(self, service: WorkbookService):
        self.service = service

    def run(self, tool_input, context):
        source = _source(context, tool_input.attachment_id)
        # Host resource ownership is authoritative; the owner dataset records the
        # already-proven conversation identity, never a model-authored session ID.
        handle = self.service.prepare(source, project_id=source.project_id, sheet=tool_input.sheet,
                                      header_row=tool_input.header_row, columns=tool_input.columns,
                                      column_types=tool_input.column_types, exclude_rows=tool_input.exclude_rows,
                                      regions=tool_input.regions,
                                      cancelled=context.is_cancelled)
        output = WorkbookPrepared(database_id=handle.id, resource_version=handle.scope_version,
                                  row_count=handle.row_count, columns=handle.columns, source=handle.source)
        return ToolOutcome(output=output, artifacts=(ArtifactDraft(
            key="workbook", type=WORKBOOK_ARTIFACT_TYPE, title="工作簿分析来源", summary=f"已准备{handle.row_count}行明细",
            visibility=ArtifactVisibility.SUPPORTING, payload=output.model_dump(mode="json"),
            resource_refs=tuple(context.scopes(ATTACHMENT_RESOURCE_KIND)),
        ),))

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="工作簿明细准备未完成。")
        source = output.get("source", {})
        structure = {key: source[key] for key in ("attachment_id", "content_sha256", "sheet", "header_row", "regions", "unselected_nonempty_rows") if key in source}
        structure["excluded_row_numbers"] = sorted(source.get("excluded_rows", {}), key=int)
        facts = {key: output[key] for key in ("database_id", "resource_version", "table", "row_count") if key in output}
        facts.update(source=structure, column_count=len(output.get("columns", [])),
                     schema_fingerprint=hashlib.sha256(json_dumps(output.get("columns", [])).encode()).hexdigest())
        return ToolObservationProjection(summary=f"已准备{output.get('row_count', 0)}行明细；需要执行经校验的SQL才能回答统计问题。",
            facts=facts, provider_payload=output)


class WorkbookContext:
    id = "dbfox.data.workbook"

    def build(self, input):
        facts = []
        for artifact in input.recent_artifacts:
            source = artifact.payload.get("source")
            if source and artifact.artifact_type in (WORKBOOK_ARTIFACT_TYPE, "dbfox.data.sql", "dbfox.data.result_view"):
                fact = {"artifact_id": artifact.artifact_id, "type": artifact.artifact_type,
                        "source": source, "run_status": artifact.run_status,
                        "resources": [r.model_dump(mode="json") for r in artifact.resource_refs]}
                if "safeSql" in artifact.payload:
                    fact["executed_or_validated_sql"] = str(artifact.payload["safeSql"])[:1200]
                if len(json_dumps([*facts, fact])) > 3500:
                    break
                facts.append(fact)
        if not facts:
            return ()
        return (ContextFragment(source_id=self.id, source_version="1", lane="evidence",
                                content=json_dumps({"successful_tool_evidence": facts,
                                                   "instruction": "New attachment references take precedence. These records preserve source and query basis, not a mutable active file. SQL validation/preparation is not proof of execution or a completed answer. Failed/cancelled Runs are not completed analyses even when an individual tool succeeded. Revalidate a new query in the current Run; ask when the intended historical file is ambiguous."})),)
