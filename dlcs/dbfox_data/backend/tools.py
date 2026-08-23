"""Agent tools contributed by the dbfox.data System DLC."""

from __future__ import annotations

from datetime import UTC, datetime

from dbfox_dlc_api import (
    ArtifactDraft,
    ArtifactRelationDraft,
    ArtifactRelationType,
    ArtifactVisibility,
    BaseTool,
    ExtensionToolRunContext,
    ToolAdmissionContext,
    ToolAdmissionDecision,
    ToolExecutionSpec,
    ToolInputError,
    ToolObservationProjection,
    ToolOutcome,
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
)

from .artifact_contracts import (
    RESULT_VIEW_ARTIFACT_TYPE,
    SAFETY_ARTIFACT_TYPE,
    SQL_ARTIFACT_TYPE,
)
from .connection import DataConnectionBoundary
from .database_selection import select_database
from .resource_kind import DATABASE_RESOURCE_KIND
from .sql.dialect_context import canonical_sql_dialect
from .query_identity import query_fingerprint
from .sql.safety_contracts import DatabaseSafetyScope, ExecutionPolicy
from .sql.row_serializer import serialize_rows
from .sql.trust_gate import TrustGate
from .sql_admission import admit_sql_execution, resolve_validated_sql_execution
from .store import DataStateStore
from .tool_contracts import (
    QueryResultOutput,
    SqlExecuteReadonlyInput,
    SqlValidateInput,
    SqlValidateOutput,
)


class SqlValidateTool(BaseTool[SqlValidateInput, SqlValidateOutput]):
    name = "sql_validate"
    group = "query"
    description = (
        "Validate one read-only query against the selected database dialect, "
        "safety rules, and an EXPLAIN dry-run. A successful call creates an "
        "immutable SQL Artifact for later execution."
    )
    input_model = SqlValidateInput
    output_model = SqlValidateOutput
    version = "2"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("network", "filesystem_read"),
        required_resource_kinds=(DATABASE_RESOURCE_KIND,),
    )
    semantics = ToolSemanticSpec(produces=("validated_query",))
    presentation = ToolPresentation(title="验证分析 SQL", category="query")

    def __init__(self, connection: DataConnectionBoundary) -> None:
        self._connection = connection

    def run(
        self,
        tool_input: SqlValidateInput,
        context: ExtensionToolRunContext,
    ) -> ToolOutcome[SqlValidateOutput]:
        resource_ref, handle = select_database(context, tool_input.database_id)
        dialect = canonical_sql_dialect(handle.profile.provider)
        scope = DatabaseSafetyScope(
            resource_id=handle.database.id,
            exists=True,
            dialect=dialect,
            environment=handle.profile.environment,
            is_read_only=handle.profile.is_read_only,
            project_id=handle.profile.project_id,
        )
        gate = TrustGate(
            schema_validator=lambda _query: [],
            dry_run_validator=lambda sql, _parameters: self._connection.explain(handle, sql),
        )
        policy: ExecutionPolicy = (
            "user_readonly"
            if context.execution_mode == "user_requested_read"
            else "agent_readonly"
        )
        decision = gate.execution_decision(
            scope,
            tool_input.sql,
            policy=policy,
        )
        decision_payload = decision.model_dump(mode="json")
        safe_sql = str(decision.safe_sql or "")
        output = SqlValidateOutput(
            can_execute=decision.can_execute,
            requires_confirmation=decision.requires_confirmation,
            safe_sql=safe_sql,
            original_sql=decision.original_sql,
            risk_level=decision.risk_level,
            blocked_reasons=list(decision.blocked_reasons),
            messages=list(decision.messages),
            execution_safety_decision=decision_payload,
        )
        fingerprint = query_fingerprint(
            resource_ref,
            safe_sql or decision.original_sql,
        )
        safety = ArtifactDraft(
            key="safety",
            type=SAFETY_ARTIFACT_TYPE,
            title="SQL 安全检查",
            summary="可执行" if decision.can_execute else "查询被安全规则阻止",
            visibility=ArtifactVisibility.INTERNAL,
            payload={
                "canExecute": decision.can_execute,
                "requiresApproval": decision.requires_confirmation,
                "riskLevel": decision.risk_level,
                "blockedReasons": list(decision.blocked_reasons),
                "messages": list(decision.messages),
                "datasourceId": handle.database.id,
                "policy": decision.policy,
                "originalSql": decision.original_sql,
                "safeSql": safe_sql,
                "passed": decision.passed,
                "guardrail": decision.guardrail,
                "schemaWarnings": list(decision.schema_warnings),
                "scopeState": decision.scope_state,
            },
            resource_refs=(resource_ref,),
        )
        query = ArtifactDraft(
            key="sql",
            type=SQL_ARTIFACT_TYPE,
            title="分析 SQL",
            summary="已通过安全检查" if decision.can_execute else "未通过安全检查",
            visibility=ArtifactVisibility.SUPPORTING,
            payload={
                "sql": decision.original_sql,
                "safeSql": safe_sql,
                "dialect": dialect,
                "queryFingerprint": fingerprint,
                "parameters": {},
            },
            resource_refs=(resource_ref,),
            relations=(
                ArtifactRelationDraft(
                    relation=ArtifactRelationType.VALIDATED_BY,
                    draft_key="safety",
                ),
            ),
        )
        return ToolOutcome(output=output, artifacts=(safety, query))


class SqlExecuteReadonlyTool(
    BaseTool[SqlExecuteReadonlyInput, QueryResultOutput]
):
    name = "sql_execute_readonly"
    group = "query"
    description = (
        "Execute the exact query bound to one immutable dbfox.data SQL Artifact. "
        "The Data capability rechecks the Artifact graph and frozen database "
        "authority immediately before opening a read-only transaction."
    )
    input_model = SqlExecuteReadonlyInput
    output_model = QueryResultOutput
    version = "2"
    policy = ToolPolicy(
        risk_level="safe",
        requires_admission=True,
        allowed_execution_modes=("user_requested_read", "agent_autonomous_read"),
    )
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        capabilities=("network", "filesystem_read"),
        required_resource_kinds=(DATABASE_RESOURCE_KIND,),
    )
    semantics = ToolSemanticSpec(produces=("query_result",))
    presentation = ToolPresentation(title="执行只读查询", category="query")

    def __init__(
        self,
        store: DataStateStore,
        connection: DataConnectionBoundary,
    ) -> None:
        self._store = store
        self._connection = connection

    def admit(
        self,
        tool_input: SqlExecuteReadonlyInput,
        context: ToolAdmissionContext,
    ) -> ToolAdmissionDecision:
        return admit_sql_execution(
            tool_input,
            context,
            sql_artifact_type=SQL_ARTIFACT_TYPE,
            safety_artifact_type=SAFETY_ARTIFACT_TYPE,
            result_artifact_type=RESULT_VIEW_ARTIFACT_TYPE,
        )

    def cancel(self, invocation_id: str) -> None:
        self._connection.cancel(invocation_id)

    def run(
        self,
        tool_input: SqlExecuteReadonlyInput,
        context: ExtensionToolRunContext,
    ) -> ToolOutcome[QueryResultOutput]:
        validated = resolve_validated_sql_execution(
            tool_input,
            context,
            sql_artifact_type=SQL_ARTIFACT_TYPE,
            safety_artifact_type=SAFETY_ARTIFACT_TYPE,
            result_artifact_type=RESULT_VIEW_ARTIFACT_TYPE,
        )
        resource_ref, handle = select_database(context, tool_input.database_id)
        if resource_ref != validated.resource_ref:
            raise ToolInputError(
                "The admitted SQL Artifact does not bind the selected database."
            )
        requires_approval = bool(
            validated.safety_artifact.payload.get("requiresApproval")
        )
        if requires_approval and not context.approval_authorizes(
            validated.approval_subject,
            resource_ref,
        ):
            raise ToolInputError(
                "This database read requires a current approval grant."
            )

        result = self._connection.execute_readonly(
            handle,
            validated.safe_sql,
            invocation_id=context.invocation_id,
            cancellation_probe=context.is_cancelled,
        )
        returned_rows = len(result.rows)
        latency_ms = sum(
            (
                result.connect_ms,
                result.execute_ms,
                result.fetch_ms,
                result.serialize_ms,
            )
        )
        fingerprint = str(
            validated.sql_artifact.payload.get("queryFingerprint") or ""
        )
        result_ref = self._store.save_query_result(
            database_resource_id=resource_ref.id,
            resource_version=str(resource_ref.version or ""),
            query_fingerprint=fingerprint,
            columns=result.columns,
            rows=result.rows,
            source_truncated=result.truncated,
        )
        durable_result = ArtifactDraft(
            key="result",
            type=RESULT_VIEW_ARTIFACT_TYPE,
            title="查询结果",
            summary=f"返回 {returned_rows} 行、{len(result.columns)} 列",
            payload={
                "sourceSqlArtifactId": validated.sql_artifact.id,
                "queryFingerprint": fingerprint,
                "datasourceGeneration": resource_ref.version,
                "columns": result.columns,
                "rowCount": returned_rows,
                "returnedRows": returned_rows,
                "latencyMs": latency_ms,
                "executedAt": datetime.now(UTC).isoformat(),
                "truncated": result.truncated,
                "evidenceKind": "query_result",
            },
            payload_ref=result_ref,
            relations=(
                ArtifactRelationDraft(
                    relation=ArtifactRelationType.DERIVED_FROM,
                    artifact_id=validated.sql_artifact.id,
                ),
            ),
            resource_refs=(resource_ref,),
            select_if_none=True,
        )
        model_window = serialize_rows(
            result.rows[:20],
            result.columns,
            max_columns=50,
            max_cell_chars=2_000,
            max_response_bytes=24_000,
        )
        output = QueryResultOutput(
            status="success",
            success=True,
            row_count=returned_rows,
            columns=model_window.columns,
            column_types=["text"] * len(model_window.columns),
            returned_rows=returned_rows,
            truncated=result.truncated or model_window.truncated,
            rows=model_window.rows,
            safe_sql="",
            execution_time_ms=latency_ms,
            warnings=(
                ["The database result exceeded the bounded transport window."]
                if result.truncated
                else []
            ),
            audit={
                "readonly": True,
                "resourceVersion": resource_ref.version,
                "responseBytes": result.response_bytes,
                "connectMs": result.connect_ms,
                "executeMs": result.execute_ms,
                "fetchMs": result.fetch_ms,
                "serializeMs": result.serialize_ms,
            },
            latency_ms=latency_ms,
        )
        return ToolOutcome(output=output, artifacts=(durable_result,))

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="只读查询执行失败。")
        result_artifact = next(
            (
                artifact
                for artifact in artifacts
                if str(getattr(artifact, "type", "")) == RESULT_VIEW_ARTIFACT_TYPE
            ),
            None,
        )
        facts = {
            "artifact_id": str(getattr(result_artifact, "id", "") or "") or None,
            "evidence_kind": "query_result",
            "row_count": int(output.get("row_count") or 0),
            "returned_rows": int(output.get("returned_rows") or 0),
            "columns": [str(column) for column in output.get("columns") or []],
            "latency_ms": output.get("latency_ms"),
            "truncated": bool(output.get("truncated")),
        }
        return ToolObservationProjection(
            summary=f"查询执行成功，返回 {facts['returned_rows']} 行。",
            facts=facts,
            provider_payload={**facts, "rows": list(output.get("rows") or [])},
        )
