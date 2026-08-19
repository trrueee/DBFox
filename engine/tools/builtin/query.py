from __future__ import annotations

from engine.agent.repositories.artifact import ArtifactRepository
from engine.errors import ToolInputError
from engine.tools.builtin.artifacts import (
    preview_drafts,
    query_result_draft,
    sql_validation_drafts,
)
from engine.tools.builtin.contracts import (
    DataPreviewInput,
    DataPreviewOutput,
    QueryResultOutput,
    SqlExecuteReadonlyInput,
    SqlValidateInput,
    SqlValidateOutput,
)
from engine.tools.db.preview import db_preview
from engine.tools.db.sql_execution import sql_execute_readonly, sql_validate
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
    MODEL_RESULT_CELL_CHARS,
    MODEL_RESULT_WINDOW_BYTES,
    MODEL_RESULT_WINDOW_COLUMNS,
    MODEL_RESULT_WINDOW_ROWS,
    bounded_tabular_provider_payload,
    safe_observation_facts,
)
from engine.sql.row_serializer import serialize_rows


def _result_observation(
    *,
    status: str,
    output: dict,
    artifacts: list,
    evidence_kind: str,
) -> ToolObservationProjection:
    if status != "success":
        return ToolObservationProjection(summary="数据读取失败。")
    result = next(
        (
            artifact
            for artifact in artifacts
            if str(getattr(artifact, "type", "")) == "result_view"
        ),
        None,
    )
    artifact_id = str(getattr(result, "id", "") or "") or None
    columns = [str(item) for item in output.get("columns") or []]
    returned_rows = int(output.get("returned_rows") or len(output.get("rows") or []))
    durable_facts = safe_observation_facts(
        {
            "artifact_id": artifact_id,
            "evidence_kind": evidence_kind,
            "row_count": output.get("row_count", returned_rows),
            "returned_rows": returned_rows,
            "columns": columns,
            "column_count": len(columns),
            "latency_ms": output.get("latency_ms"),
            "truncated": bool(output.get("truncated")),
            "recovery": (
                "Use result_inspect with artifact_id to reload a bounded page "
                "after process recovery or when more values are needed."
            ),
        }
    )
    return ToolObservationProjection(
        summary=(
            f"数据样例读取成功，抽样返回 {returned_rows} 行。"
            if evidence_kind == "sample_rows"
            else f"查询执行成功，返回 {returned_rows} 行。"
        ),
        facts=durable_facts,
        provider_payload=bounded_tabular_provider_payload(
            facts=durable_facts,
            columns=columns,
            rows=list(output.get("rows") or []),
            total_returned_rows=returned_rows,
            source_truncated=bool(output.get("truncated")),
        ),
    )


class DataPreviewTool(BaseTool[DataPreviewInput, DataPreviewOutput]):
    name = "data_preview"
    group = "query"
    description = (
        "Read at most 20 redacted sample rows from one catalog-validated table. "
        "This proves only row shape and example values; it never proves aggregates, "
        "trends, rankings, rates, distributions, or causality."
    )
    input_model = DataPreviewInput
    output_model = DataPreviewOutput
    presentation = ToolPresentation(title="查看数据样例", category="query")
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read", "database_read"),
        required_resource_kinds=("database",),
    )
    semantics = ToolSemanticSpec(produces=(ToolSemanticCapability.SAMPLE_ROWS,))

    def run(
        self,
        tool_input: DataPreviewInput,
        context: ToolRunContext,
    ) -> ToolOutcome[DataPreviewOutput]:
        db = context.require_database()
        request = context.require_request()
        output = DataPreviewOutput.model_validate(
            db_preview(
                db,
                request.datasource_id,
                table=tool_input.table,
                columns=tool_input.columns,
                limit=tool_input.limit,
                where=(
                    tool_input.where.model_dump(mode="json")
                    if tool_input.where
                    else None
                ),
                order_by=[
                    item.model_dump(mode="json")
                    for item in (tool_input.order_by or [])
                ]
                or None,
            )
        )
        return ToolOutcome(
            output=output,
            artifacts=preview_drafts(
                db,
                request.datasource_id,
                request.datasource_generation,
                output,
            ),
        )

    def project_observation(self, *, status, output, artifacts):
        return _result_observation(
            status=status,
            output=output,
            artifacts=artifacts,
            evidence_kind="sample_rows",
        )


class SqlValidateTool(BaseTool[SqlValidateInput, SqlValidateOutput]):
    name = "sql_validate"
    group = "query"
    description = (
        "Validate one read-only SELECT against dialect, schema, and safety policy "
        "without reading data. A successful call creates an immutable SQL Artifact; "
        "pass that exact Artifact ID to sql_execute_readonly."
    )
    input_model = SqlValidateInput
    output_model = SqlValidateOutput
    presentation = ToolPresentation(title="验证分析 SQL", category="query")
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read",),
        required_resource_kinds=("database",),
    )
    semantics = ToolSemanticSpec(
        produces=(ToolSemanticCapability.VALIDATED_QUERY,),
        # Validation is the required hand-off into execution. ProgressGuard
        # collapses repeated validations to the bounded readiness states, so a
        # newly executable query gets one continuation without making SQL churn
        # an unlimited source of progress.
        contributes_progress=True,
    )

    def run(
        self,
        tool_input: SqlValidateInput,
        context: ToolRunContext,
    ) -> ToolOutcome[SqlValidateOutput]:
        db = context.require_database()
        request = context.require_request()
        raw = sql_validate(
            db,
            request.datasource_id,
            tool_input.sql,
            request.question,
        )
        output = SqlValidateOutput(
            can_execute=bool(raw.get("can_execute")),
            requires_confirmation=bool(raw.get("requires_confirmation")),
            safe_sql=str(raw.get("safe_sql") or ""),
            original_sql=str(raw.get("original_sql") or tool_input.sql),
            risk_level=str(raw.get("risk_level") or "safe"),
            blocked_reasons=[str(item) for item in raw.get("blocked_reasons") or []],
            messages=[str(item) for item in raw.get("messages") or []],
            execution_safety_decision=raw.get("execution_safety_decision") or {},
        )
        return ToolOutcome(
            output=output,
            artifacts=sql_validation_drafts(
                db,
                request.datasource_id,
                output,
            ),
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="SQL 安全检查失败。")
        sql_artifact = next(
            (
                artifact
                for artifact in artifacts
                if str(getattr(artifact, "type", "")) == "sql"
            ),
            None,
        )
        artifact_id = str(getattr(sql_artifact, "id", "") or "") or None
        can_execute = bool(output.get("can_execute"))
        return ToolObservationProjection(
            summary=("SQL 已通过安全检查。" if can_execute else "SQL 未通过安全检查。"),
            facts=safe_observation_facts(
                {
                    "can_execute": can_execute,
                    "requires_confirmation": bool(output.get("requires_confirmation")),
                    "validation_artifact_id": artifact_id,
                    "risk_level": output.get("risk_level"),
                    "blocked_reasons": output.get("blocked_reasons") or [],
                    "messages": output.get("messages") or [],
                }
            ),
        )


class SqlExecuteReadonlyTool(BaseTool[SqlExecuteReadonlyInput, QueryResultOutput]):
    name = "sql_execute_readonly"
    group = "query"
    description = (
        "Execute the exact SQL bound to one immutable validation Artifact. Do not "
        "send SQL text. The Runtime independently reloads and verifies the Artifact, "
        "rejects re-execution, and pauses for approval when policy requires it."
    )
    input_model = SqlExecuteReadonlyInput
    output_model = QueryResultOutput
    presentation = ToolPresentation(title="执行只读查询", category="query")
    policy = ToolPolicy(risk_level="safe", requires_validated_sql=True)
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read", "database_read"),
        required_resource_kinds=("database",),
    )
    semantics = ToolSemanticSpec(produces=(ToolSemanticCapability.QUERY_RESULT,))

    def run(
        self,
        tool_input: SqlExecuteReadonlyInput,
        context: ToolRunContext,
    ) -> ToolOutcome[QueryResultOutput]:
        db = context.require_database()
        request = context.require_request()
        repository = ArtifactRepository(db)
        try:
            validated = repository.require_validated_sql(
                session_id=request.session_id,
                run_id=request.run_id,
                sql_artifact_id=tool_input.validation_artifact_id,
            )
        except ValueError as exc:
            raise ToolInputError(str(exc)) from exc
        existing = repository.result_for_sql_artifact(
            session_id=request.session_id,
            run_id=request.run_id,
            sql_artifact_id=tool_input.validation_artifact_id,
        )
        if existing is not None:
            raise ToolInputError(
                "This validated SQL was already executed as Result Artifact "
                f"{existing.id}; reuse that result instead of executing it again."
            )
        raw = sql_execute_readonly(
            db,
            request.datasource_id,
            question=request.question,
            safety=validated.safety,
            execution_id=request.execution_id or None,
            expected_connection_generation=request.datasource_generation,
            execution_authority=context.execution_authority,
        )
        output = QueryResultOutput(
            status="success",
            success=True,
            row_count=int(raw.get("rowCount") or 0),
            columns=[str(item) for item in raw.get("columns") or []],
            column_types=[str(item) for item in raw.get("column_types") or []],
            returned_rows=int(raw.get("returned_rows") or 0),
            truncated=bool(raw.get("truncated")),
            rows=list(raw.get("rows") or []),
            safe_sql=str(raw.get("safe_sql") or ""),
            execution_time_ms=float(raw.get("execution_time_ms") or 0),
            explain_plan=raw.get("explain_plan"),
            warnings=[str(item) for item in raw.get("warnings") or []],
            audit=raw.get("audit") or {},
            latency_ms=int(raw.get("latency_ms") or 0),
        )
        result_draft = query_result_draft(
            db,
            request.datasource_id,
            tool_input.validation_artifact_id,
            request.datasource_generation,
            output,
        )
        model_window = serialize_rows(
            output.rows[:MODEL_RESULT_WINDOW_ROWS],
            output.columns,
            max_columns=MODEL_RESULT_WINDOW_COLUMNS,
            max_cell_chars=MODEL_RESULT_CELL_CHARS,
            max_response_bytes=MODEL_RESULT_WINDOW_BYTES,
        )
        bounded_output = output.model_copy(
            update={
                "columns": model_window.columns,
                "column_types": output.column_types[: len(model_window.columns)],
                "rows": model_window.rows,
                # The durable Result Artifact and query-history payload are the
                # source of truth. The immediate function result is only the
                # bounded model window used by project_observation().
                "safe_sql": "",
                "explain_plan": None,
                "warnings": [],
                "audit": {
                    "history_id": output.audit.get("history_id"),
                    "execution_id": output.audit.get("execution_id"),
                },
            }
        )
        return ToolOutcome(
            output=bounded_output,
            artifacts=(result_draft,),
        )

    def project_observation(self, *, status, output, artifacts):
        return _result_observation(
            status=status,
            output=output,
            artifacts=artifacts,
            evidence_kind="query_result",
        )
