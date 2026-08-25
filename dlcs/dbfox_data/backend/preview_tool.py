"""Structured, catalog-validated sample-row preview for dbfox.data."""

from __future__ import annotations

from datetime import UTC, datetime
import time
from typing import Any

from dbfox_dlc_api import (
    ArtifactDraft,
    ArtifactRelationDraft,
    ArtifactRelationType,
    ArtifactVisibility,
    BaseTool,
    ExtensionToolRunContext,
    ToolExecutionSpec,
    ToolResourceRequirement,
    ToolInputError,
    ToolObservationProjection,
    ToolOutcome,
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
)

from .artifact_contracts import RESULT_VIEW_ARTIFACT_TYPE, SQL_ARTIFACT_TYPE
from .connection import DataConnectionBoundary
from .database_selection import select_database
from .query_identity import query_fingerprint
from .resource_kind import DATABASE_RESOURCE_KIND
from .sensitivity import SENSITIVE_FALLBACK, is_sensitive_name, redact_row
from .sql.builder import build_select
from .sql.row_serializer import serialize_rows
from .store import DataStateStore
from .tool_contracts import DataPreviewInput, DataPreviewOutput


class DataPreviewTool(BaseTool[DataPreviewInput, DataPreviewOutput]):
    name = "data_preview"
    group = "query"
    description = (
        "Read at most 20 redacted sample rows from one catalog-validated table. "
        "This proves row shape and example values only, never aggregates or trends."
    )
    input_model = DataPreviewInput
    output_model = DataPreviewOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("network", "filesystem_read"),
        required_resources=(ToolResourceRequirement(kind=DATABASE_RESOURCE_KIND, selector_field="database_id"),),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.data.sample_rows",))
    presentation = ToolPresentation(title="查看数据样例", category="query")

    def __init__(
        self,
        store: DataStateStore,
        connection: DataConnectionBoundary,
    ) -> None:
        self._store = store
        self._connection = connection

    def cancel(self, invocation_id: str) -> None:
        self._connection.cancel(invocation_id)

    def run(
        self,
        tool_input: DataPreviewInput,
        context: ExtensionToolRunContext,
    ) -> ToolOutcome[DataPreviewOutput]:
        started = time.perf_counter()
        resource_ref, handle = select_database(context, tool_input.database_id)
        try:
            table, catalog_columns = self._store.resolve_catalog_table(
                handle.database.id,
                tool_input.table,
            )
        except KeyError as exc:
            raise ToolInputError(
                "Table is unavailable in the current catalog; refresh or browse the catalog first."
            ) from exc
        except ValueError as exc:
            raise ToolInputError(str(exc)) from exc

        available = {
            str(column["column_name"]): column
            for column in catalog_columns
        }
        requested = list(tool_input.columns or [])
        if not requested:
            requested = [
                name
                for name in available
                if not is_sensitive_name(name)
            ][:8]
            if not requested:
                requested = list(available)[:8]
        referenced = [*requested]
        if tool_input.where is not None:
            referenced.append(tool_input.where.column)
        referenced.extend(item.column for item in (tool_input.order_by or []))
        unknown = [
            name
            for name in dict.fromkeys(referenced)
            if name not in available
        ]
        if unknown:
            raise ToolInputError(
                "Columns are unavailable in the current catalog: "
                + ", ".join(unknown)
            )
        if not requested:
            raise ToolInputError("The selected table has no previewable columns.")

        where = (
            tool_input.where.model_dump(mode="json")
            if tool_input.where is not None
            else None
        )
        order = [
            item.model_dump(mode="json")
            for item in (tool_input.order_by or [])
        ] or None
        safe_sql, parameters = build_select(
            table=str(table["table_name"]),
            table_schema=str(table["schema_name"] or "") or None,
            columns=requested,
            where=where,
            order=order,
            limit=tool_input.limit,
            dialect=handle.profile.provider,
            catalog_validated_identifiers=True,
        )
        try:
            result = self._connection.execute_readonly(
                handle,
                safe_sql,
                invocation_id=context.invocation_id,
                cancellation_probe=context.is_cancelled,
                parameters=parameters,
            )
        except Exception as exc:
            raise ToolInputError("Database preview execution failed.") from exc

        sensitive_columns = {
            name
            for name in requested
            if is_sensitive_name(name)
        }
        redacted_rows = [
            redact_row(
                row,
                SENSITIVE_FALLBACK,
                sensitive_columns=sensitive_columns,
            )
            for row in result.rows
        ]
        model_window = serialize_rows(
            redacted_rows,
            requested,
            max_columns=32,
            max_cell_chars=2_000,
            max_response_bytes=24_000,
        )
        latency_ms = int((time.perf_counter() - started) * 1_000)
        fingerprint = query_fingerprint(resource_ref, safe_sql, parameters)
        result_ref = self._store.save_query_result(
            database_resource_id=resource_ref.id,
            resource_version=str(resource_ref.version or ""),
            query_fingerprint=fingerprint,
            columns=requested,
            rows=redacted_rows,
            source_truncated=result.truncated,
        )
        source = ArtifactDraft(
            key="preview_sql",
            type=SQL_ARTIFACT_TYPE,
            title="数据预览 SQL",
            summary="受限抽样查询来源",
            visibility=ArtifactVisibility.SUPPORTING,
            payload={
                "sql": safe_sql,
                "safeSql": safe_sql,
                "dialect": handle.profile.provider,
                "queryFingerprint": fingerprint,
                "parameters": parameters,
            },
            resource_refs=(resource_ref,),
        )
        sample = ArtifactDraft(
            key="sample",
            type=RESULT_VIEW_ARTIFACT_TYPE,
            title="数据样例",
            summary=f"抽样返回 {len(model_window.rows)} 行、{len(model_window.columns)} 列",
            payload={
                "sourceSqlArtifactId": "",
                "queryFingerprint": fingerprint,
                "datasourceGeneration": resource_ref.version,
                "columns": model_window.columns,
                "rowCount": len(redacted_rows),
                "returnedRows": len(redacted_rows),
                "latencyMs": latency_ms,
                "executedAt": datetime.now(UTC).isoformat(),
                "truncated": result.truncated or model_window.truncated,
                "evidenceKind": "sample_rows",
            },
            payload_ref=result_ref,
            payload_draft_refs={"sourceSqlArtifactId": "preview_sql"},
            relations=(
                ArtifactRelationDraft(
                    relation=ArtifactRelationType.DERIVED_FROM,
                    draft_key="preview_sql",
                ),
            ),
            resource_refs=(resource_ref,),
            select_if_none=True,
        )
        qualified_name = ".".join(
            part
            for part in (
                str(table["schema_name"] or ""),
                str(table["table_name"]),
            )
            if part
        )
        warnings = []
        if sensitive_columns:
            warnings.append("Sensitive sample values were redacted.")
        if result.truncated or model_window.truncated:
            warnings.append("The preview exceeded the bounded response window.")
        output = DataPreviewOutput(
            table=qualified_name,
            columns=model_window.columns,
            returned_rows=len(model_window.rows),
            limit_applied=tool_input.limit,
            rows=model_window.rows,
            safe_sql=safe_sql,
            parameters=parameters,
            truncated=result.truncated or model_window.truncated,
            warnings=warnings,
            column_summaries=[
                {
                    "name": name,
                    "type": str(
                        available[name].get("column_type")
                        or available[name].get("data_type")
                        or ""
                    ),
                    "nullable": bool(available[name].get("is_nullable")),
                    "sensitive": is_sensitive_name(name),
                }
                for name in model_window.columns
            ],
            audit={
                "readonlyChecked": True,
                "catalogValidated": True,
                "limitEnforced": True,
                "resourceVersion": resource_ref.version,
            },
            latency_ms=latency_ms,
        )
        return ToolOutcome(output=output, artifacts=(source, sample))

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="数据样例读取失败。")
        result_artifact = next(
            (
                artifact
                for artifact in artifacts
                if str(getattr(artifact, "type", "")) == RESULT_VIEW_ARTIFACT_TYPE
            ),
            None,
        )
        columns = [str(column) for column in output.get("columns") or []]
        returned_rows = int(output.get("returned_rows") or 0)
        facts: dict[str, Any] = {
            "artifact_id": str(getattr(result_artifact, "id", "") or "") or None,
            "evidence_kind": "sample_rows",
            "table": output.get("table"),
            "returned_rows": returned_rows,
            "columns": columns,
            "truncated": bool(output.get("truncated")),
        }
        return ToolObservationProjection(
            summary=f"数据样例读取成功，抽样返回 {returned_rows} 行。",
            facts=facts,
            provider_payload={**facts, "rows": list(output.get("rows") or [])},
        )
