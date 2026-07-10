"""Agent API Router — consolidated /agent/* entry points.

This module replaces the legacy engine/api/ai.py which mixed agent run routes
with old Text-to-SQL (/query/generate), golden-sql, and llm-logs endpoints.

Phase 1 (2026-06): All agent routes consolidated under /agent/*.
Old /query/agent-* paths are removed.
"""

from __future__ import annotations

import json
import logging
import time as _time
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.agent import DBFoxAgentRuntime
from engine.agent.app.error_boundary import (
    AgentOperation,
    PublicAgentFailure,
    public_agent_failure,
    safe_agent_log,
)
from engine.agent_core import persistence as agent_persistence
from engine.agent_core.artifacts import AgentArtifactIdentity, build_agent_artifacts
from engine.agent_core.types import (
    AgentArtifact,
    AgentApprovalDecisionRequest,
    AgentResumeRequest,
    AgentRunRequest,
    AgentRunResponse,
    AgentRuntimeEvent,
)
from engine.agent_core.events import EventEmitter
from engine.app.errors import public_error
from engine.db import get_db
from engine.errors import DBFoxError
from engine.llm.config import (
    normalize_product_llm_preferences,
    resolve_product_llm_config_from_credential,
)
from engine.llm.factory import LlmCallOptions, create_chat_model
from engine.models import DataSource
from engine.policy.engine import PolicyEngine
from engine.sql.dialect_context import DialectContext
from engine.sql.execution.streaming_executor import export_max_rows_from_env
from engine.sql.result_view.models import (
    ResultExportQuery as ServiceResultExportQuery,
    ResultFilter as ServiceResultFilter,
    ResultPageQuery as ServiceResultPageQuery,
    ResultSort as ServiceResultSort,
    ResultSourceRef,
    TableExportQuery as ServiceTableExportQuery,
    TablePageQuery as ServiceTablePageQuery,
    TableSourceRef,
    ResultViewError,
)
from engine.sql.result_view.service import ResultViewService
from engine.sql.safety.service import SqlSafetyService

logger = logging.getLogger("dbfox.api.agent")
router = APIRouter()


class LlmTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_credential_id: str
    api_base: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"


class LlmTestResponse(BaseModel):
    ok: bool
    model: str
    api_base: str
    latency_ms: int
    error_code: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# LLM connection test — POST /agent/llm/test
# ---------------------------------------------------------------------------

@router.post("/agent/llm/test", response_model=LlmTestResponse)
def api_llm_test(req: LlmTestRequest) -> LlmTestResponse:
    """Test LLM API connectivity with a minimal chat completion call.

    This endpoint resolves an opaque credential through the local OS vault and
    validates that it can reach the target LLM service.
    """
    t0 = _time.monotonic()
    try:
        config = resolve_product_llm_config_from_credential(
            llm_credential_id=req.llm_credential_id,
            api_base=req.api_base,
            model_name=req.model_name,
        )
        client = create_chat_model(
            config,
            LlmCallOptions(timeout=10.0, max_tokens=1),
        )
        # Minimal invocation to verify auth + connectivity + model existence.
        client.invoke("ping")
        latency_ms = int((_time.monotonic() - t0) * 1000)
        return LlmTestResponse(
            ok=True,
            model=config.model_name,
            api_base=config.api_base,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = int((_time.monotonic() - t0) * 1000)
        failure = public_agent_failure(exc, operation="llm_test")
        safe_agent_log(logger, operation="llm_test", exc=exc)
        return LlmTestResponse(
            ok=False,
            model=req.model_name,
            api_base=req.api_base,
            latency_ms=latency_ms,
            error_code=failure.code,
            error_message=failure.message,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _normalize_agent_run_llm_config(req: AgentRunRequest) -> AgentRunRequest:
    preferences = normalize_product_llm_preferences(
        llm_credential_id=req.llm_credential_id,
        api_base=req.api_base,
        model_name=req.model_name,
    )
    return req.model_copy(
        update={
            "api_base": preferences.api_base,
            "model_name": preferences.model_name,
        }
    )


def _format_sse_event(event: AgentRuntimeEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def attach_conversation_event_ids(event: AgentRuntimeEvent, req: AgentRunRequest) -> AgentRuntimeEvent:
    conversation_id = req.conversation_id or req.session_id
    if conversation_id:
        event.conversation_id = conversation_id
    if req.user_message_id:
        event.user_message_id = req.user_message_id
    if req.assistant_message_id:
        event.assistant_message_id = req.assistant_message_id
        event.message_id = event.message_id or req.assistant_message_id
    return event


def sse_failed_event(
    event_id: str,
    run_id: str,
    failure: PublicAgentFailure,
) -> str:
    """Build a formatted SSE error event string."""
    payload = {
        "event_id": event_id,
        "run_id": run_id,
        "sequence": 1,
        "created_at_ms": 0,
        "type": "agent.run.failed",
        "error": failure.message,
        "response": None,
        "code": failure.code,
    }
    return f"event: agent.run.failed\ndata: {json.dumps(payload)}\n\n"


def _http_detail(exc: DBFoxError) -> dict[str, str]:
    detail = public_error(exc.code, exc)
    return {"code": str(detail["code"]), "message": str(detail["message"])}


def _agent_http_exception(exc: Exception, *, operation: AgentOperation) -> HTTPException:
    failure = public_agent_failure(exc, operation=operation)
    safe_agent_log(logger, operation=operation, exc=exc)
    return HTTPException(status_code=failure.status_code, detail=failure.detail())


# ---------------------------------------------------------------------------
# Agent run — GET routes
# ---------------------------------------------------------------------------

@router.get("/agent/runs/{run_id}", response_model=AgentRunResponse | None)
def api_get_agent_run(run_id: str, db: Session = Depends(get_db)) -> AgentRunResponse | None:
    result = agent_persistence.get_run(db, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"Agent run {run_id} not found."})
    return result


@router.get("/agent/sessions/{session_id}/runs")
def api_list_session_runs(session_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return agent_persistence.list_session_runs(db, session_id)


@router.get("/agent/runs/recent", response_model=AgentRunResponse | None)
def api_get_recent_agent_run(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> AgentRunResponse | None:
    result = agent_persistence.get_recent_run(db, datasource_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "NO_RECENT_RUN", "message": "No recent agent run found for this datasource."})
    return result


@router.get("/agent/runs/{run_id}/artifacts")
def api_get_run_artifacts(run_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return agent_persistence.list_run_artifacts(db, run_id)


@router.get("/agent/runs/{run_id}/events")
def api_get_run_events(run_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return agent_persistence.list_run_events(db, run_id)


@router.get("/agent/runs/{run_id}/trace")
def api_get_run_trace(run_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return agent_persistence.list_run_trace_events(db, run_id)


@router.get("/agent/runs/{run_id}/approvals")
def api_get_run_approvals(run_id: str, db: Session = Depends(get_db)) -> list[Any]:
    return agent_persistence.list_run_approvals(db, run_id)


@router.get("/agent/runs/{run_id}/checkpoints")
def api_get_run_checkpoints(run_id: str, db: Session = Depends(get_db)) -> list[Any]:
    return agent_persistence.list_checkpoints(db, run_id)


# ---------------------------------------------------------------------------
# Agent run — POST routes (non-streaming)
# ---------------------------------------------------------------------------

@router.post("/agent/run", response_model=AgentRunResponse)
def api_agent_run(req: AgentRunRequest, db: Session = Depends(get_db)) -> AgentRunResponse:
    try:
        normalized_req = _normalize_agent_run_llm_config(req)
        return DBFoxAgentRuntime(db).run(normalized_req)
    except Exception as exc:
        db.rollback()
        raise _agent_http_exception(exc, operation="run") from exc


@router.post("/agent/runs/{run_id}/resume", response_model=AgentRunResponse)
def api_agent_run_resume(
    run_id: str,
    req: AgentResumeRequest,
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    try:
        return DBFoxAgentRuntime(db).resume(run_id, req.approval_id)
    except Exception as exc:
        db.rollback()
        raise _agent_http_exception(exc, operation="resume") from exc


@router.post("/agent/runs/{run_id}/cancel")
def api_cancel_agent_run(
    run_id: str,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Cancel a running agent run. Marks the run as cancelled in the database.
    The frontend should also abort the SSE stream via AbortController."""
    try:
        agent_persistence.cancel_run(db, run_id=run_id)
        db.commit()
        return {"status": "cancelled", "run_id": run_id}
    except Exception as exc:
        db.rollback()
        raise _agent_http_exception(exc, operation="cancel") from exc


@router.post("/agent/runs/{run_id}/approvals/{approval_id}")
def api_resolve_agent_approval(
    run_id: str,
    approval_id: str,
    req: AgentApprovalDecisionRequest,
    db: Session = Depends(get_db),
) -> Any:
    try:
        approval = agent_persistence.resolve_approval(
            db,
            run_id=run_id,
            approval_id=approval_id,
            decision=req.decision,
            note=req.note,
        )
        emitter = EventEmitter(
            run_id,
            lambda event: agent_persistence.record_runtime_event(db, approval.session_id, event),
            start_sequence=agent_persistence.get_latest_runtime_event_sequence(db, run_id),
        )
        emitter.emit(
            "agent.approval.resolved",
            step={"name": approval.step_name, "status": approval.status},
            approval=approval,
        )
        if approval.status == "rejected":
            emitter.emit("agent.run.failed", error="Approval rejected")
        db.commit()
        return approval
    except DBFoxError as exc:
        db.rollback()
        raise _agent_http_exception(exc, operation="approval") from exc
    except Exception as exc:
        db.rollback()
        raise _agent_http_exception(exc, operation="approval") from exc


# ---------------------------------------------------------------------------
# Agent run — SSE streaming routes
# ---------------------------------------------------------------------------

@router.post("/agent/run/stream")
def api_agent_run_stream(req: AgentRunRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    def stream_events() -> Any:  # noqa
        try:
            normalized_req = _normalize_agent_run_llm_config(req)
            for event in DBFoxAgentRuntime(db).run_iter(normalized_req):
                attach_conversation_event_ids(event, normalized_req)
                yield _format_sse_event(event)
        except Exception as exc:
            db.rollback()
            failure = public_agent_failure(exc, operation="run")
            safe_agent_log(logger, operation="run", exc=exc)
            yield sse_failed_event("runtime_error", "", failure)

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agent/runs/{run_id}/resume/stream")
def api_agent_run_resume_stream(
    run_id: str,
    req: AgentResumeRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    def stream_events() -> Any:  # noqa
        try:
            for event in DBFoxAgentRuntime(db).resume_iter(run_id, req.approval_id):
                yield _format_sse_event(event)
        except Exception as exc:
            db.rollback()
            failure = public_agent_failure(exc, operation="resume")
            safe_agent_log(logger, operation="resume", exc=exc, run_id=run_id)
            yield sse_failed_event("runtime_resume_error", run_id, failure)

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# SQL Console — artifact-backed execution
# ---------------------------------------------------------------------------

class ConsoleExecuteRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    datasourceId: str = Field(min_length=1, max_length=128)
    sql: str = Field(min_length=1, max_length=200_000)
    question: str | None = Field(default=None, max_length=20_000)
    sessionId: str | None = Field(default=None, min_length=1, max_length=128)
    executionId: str | None = Field(default=None, min_length=1, max_length=128)


class ConsoleExecuteResponse(BaseModel):
    runId: str
    sessionId: str
    sqlArtifactId: str
    safetyArtifactId: str | None = None
    resultArtifactId: str | None = None
    artifacts: list[AgentArtifact]
    warnings: list[str] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


def _console_safety_payload(decision: Any, *, dialect: str) -> dict[str, Any]:
    return {
        "passed": bool(decision.passed),
        "can_execute": bool(decision.can_execute),
        "requires_confirmation": bool(decision.requires_confirmation),
        "guardrail": decision.guardrail,
        "schema_warnings": list(decision.schema_warnings or []),
        "messages": list(decision.messages or []),
        "policy": decision.policy,
        "safe_sql": decision.safe_sql,
        "original_sql": decision.original_sql,
        "dialect": dialect,
    }


def _console_execution_summary(execution: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": bool(execution.get("success")),
        "rowCount": int(execution.get("rowCount") or 0),
        "columns": list(execution.get("columns") or []),
        "latencyMs": int(execution.get("latencyMs") or 0),
        "truncated": bool(execution.get("truncated")),
        "historyId": execution.get("historyId"),
        "executionId": execution.get("executionId"),
        "warnings": list(execution.get("warnings") or []),
        "notices": list(execution.get("notices") or []),
    }


def _artifact_id_by_type(artifacts: list[AgentArtifact], artifact_type: str) -> str | None:
    for artifact in artifacts:
        if artifact.type == artifact_type:
            return artifact.id
    return None


@router.post("/agent/console/execute", response_model=ConsoleExecuteResponse)
def api_agent_console_execute(req: ConsoleExecuteRequest, db: Session = Depends(get_db)) -> ConsoleExecuteResponse:
    datasource = db.query(DataSource).filter(DataSource.id == req.datasourceId).first()
    if not datasource:
        raise HTTPException(status_code=404, detail=public_error("DATASOURCE_NOT_FOUND", "Datasource not found."))

    sql = req.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail=public_error("SQL_EMPTY", "SQL cannot be empty."))

    run_id = f"console-run-{uuid4()}"
    session_id = (req.sessionId or f"console-session-{req.datasourceId}").strip()
    question = (req.question or "SQL Console").strip() or "SQL Console"

    try:
        PolicyEngine.enforce_query_policy(datasource, sql)
        ctx = DialectContext.from_datasource(datasource)
        decision = SqlSafetyService(db).build_execution_decision(sql, ctx, policy="user_readonly")

        from engine.sql.executor import execute_query

        execution = execute_query(
            db,
            req.datasourceId,
            sql,
            question,
            req.executionId,
            safety_decision=decision,
            safety_policy="user_readonly",
        )

        safe_sql = str(decision.safe_sql or "").strip()
        execution_for_artifact = {
            **execution,
            "sql": safe_sql,
            "safe_sql": safe_sql,
            "dialect": ctx.sqlglot_dialect,
        }
        safety = _console_safety_payload(decision, dialect=ctx.sqlglot_dialect)
        identity = AgentArtifactIdentity(run_id)
        artifacts = build_agent_artifacts(
            query_plan=None,
            sql=safe_sql,
            safety=safety,
            execution=execution_for_artifact,
            chart_suggestion=None,
            answer=None,
            datasource_id=req.datasourceId,
            identity=identity,
        )
        sql_artifact_id = _artifact_id_by_type(artifacts, "sql")
        if not sql_artifact_id:
            raise DBFoxError("Console execution did not produce a SQL artifact.", code="CONSOLE_SQL_ARTIFACT_MISSING")

        run_req = AgentRunRequest(
            datasource_id=req.datasourceId,
            question=question,
            session_id=session_id,
            conversation_id=session_id,
            execute=True,
            execution_mode="user_requested_read",
        )
        agent_persistence.create_or_get_session(db, run_req, run_id)
        agent_persistence.start_run(db, run_req, run_id, session_id)
        for index, artifact in enumerate(artifacts, start=1):
            agent_persistence.record_artifact(db, session_id, run_id, artifact, index)

        response_for_storage = AgentRunResponse(
            run_id=run_id,
            session_id=session_id,
            conversation_id=session_id,
            success=True,
            status="completed",
            question=question,
            sql=safe_sql,
            safety=safety,
            execution=_console_execution_summary(execution),
            artifacts=artifacts,
            explanation="SQL Console execution completed as SQL-backed artifacts.",
        )
        agent_persistence.complete_run(db, response_for_storage)
        db.commit()
        return ConsoleExecuteResponse(
            runId=run_id,
            sessionId=session_id,
            sqlArtifactId=sql_artifact_id,
            safetyArtifactId=_artifact_id_by_type(artifacts, "safety"),
            resultArtifactId=_artifact_id_by_type(artifacts, "result_view"),
            artifacts=artifacts,
            warnings=list(execution.get("warnings") or []),
            notices=list(execution.get("notices") or []),
        )
    except DBFoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=_http_detail(exc))
    except Exception as exc:
        db.rollback()
        logger.exception("SQL Console artifact execution failed")
        raise HTTPException(status_code=500, detail=public_error("CONSOLE_EXECUTION_ERROR", exc))

# ---------------------------------------------------------------------------
# Agent Result Pagination API
# ---------------------------------------------------------------------------

class ResultSort(BaseModel):
    column: str
    direction: Literal["asc", "desc"]

class ResultFilter(BaseModel):
    column: str
    operator: str
    value: Any

class ResultPageRequest(BaseModel):
    datasourceId: str
    sourceSqlArtifactId: str
    safeSql: str
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=500)
    sort: list[ResultSort] | None = None
    filters: list[ResultFilter] | None = None
    search: str | None = None
    countMode: Literal["none", "exact", "estimate"] = "none"

class TableResultPageRequest(BaseModel):
    datasourceId: str
    tableId: str | None = None
    tableName: str
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=500)
    sort: list[ResultSort] | None = None
    filters: list[ResultFilter] | None = None
    search: str | None = None
    countMode: Literal["none", "exact", "estimate"] = "none"

class TableResultExportRequest(BaseModel):
    datasourceId: str
    tableId: str | None = None
    tableName: str
    sort: list[ResultSort] | None = None
    filters: list[ResultFilter] | None = None
    search: str | None = None

class ResultExportRequest(BaseModel):
    datasourceId: str
    sourceSqlArtifactId: str
    safeSql: str
    sort: list[ResultSort] | None = None
    filters: list[ResultFilter] | None = None
    search: str | None = None

class ResultPageResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    page: int
    pageSize: int
    rowCount: int | None = None
    hasNextPage: bool
    executedSql: str
    latencyMs: int
    warnings: list[str] | None = None
    notices: list[str] | None = None


def _result_source_ref(req: ResultPageRequest | ResultExportRequest) -> ResultSourceRef:
    return ResultSourceRef(
        datasource_id=req.datasourceId,
        source_sql_artifact_id=req.sourceSqlArtifactId,
        safe_sql=req.safeSql,
    )


def _table_source_ref(req: TableResultPageRequest | TableResultExportRequest) -> TableSourceRef:
    return TableSourceRef(
        datasource_id=req.datasourceId,
        table_id=req.tableId,
        table_name=req.tableName,
    )


def _result_filters(filters: list[ResultFilter] | None) -> list[ServiceResultFilter]:
    return [ServiceResultFilter.model_validate(item.model_dump()) for item in (filters or [])]


def _result_sorts(sorts: list[ResultSort] | None) -> list[ServiceResultSort]:
    return [ServiceResultSort.model_validate(item.model_dump()) for item in (sorts or [])]


def _result_view_http_error(exc: ResultViewError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=public_error(exc.code, exc.message),
    )

@router.post("/agent/results/page", response_model=ResultPageResponse)
def api_agent_result_page(req: ResultPageRequest, db: Session = Depends(get_db)) -> ResultPageResponse:
    from engine.models import DataSource

    ds = db.query(DataSource).filter(DataSource.id == req.datasourceId).first()
    if not ds:
        raise HTTPException(status_code=404, detail=public_error("DATASOURCE_NOT_FOUND", "Datasource not found."))

    try:
        result = ResultViewService(db).page(
            ServiceResultPageQuery(
                source=_result_source_ref(req),
                filters=_result_filters(req.filters),
                sort=_result_sorts(req.sort),
                search=req.search,
                page=req.page,
                page_size=req.pageSize,
                count_mode=req.countMode,
            )
        )
    except ResultViewError as e:
        raise _result_view_http_error(e)
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        logger.exception("Failed to execute derived query")
        raise HTTPException(status_code=500, detail=public_error("EXECUTION_ERROR", e))

    return ResultPageResponse(
        columns=result.columns,
        rows=result.rows,
        page=result.page,
        pageSize=result.page_size,
        rowCount=result.row_count,
        hasNextPage=result.has_next_page,
        executedSql=result.executed_sql,
        latencyMs=result.latency_ms,
        warnings=result.warnings,
        notices=result.notices,
    )


@router.post("/agent/results/table/page", response_model=ResultPageResponse)
def api_agent_table_result_page(req: TableResultPageRequest, db: Session = Depends(get_db)) -> ResultPageResponse:
    from engine.models import DataSource

    ds = db.query(DataSource).filter(DataSource.id == req.datasourceId).first()
    if not ds:
        raise HTTPException(status_code=404, detail=public_error("DATASOURCE_NOT_FOUND", "Datasource not found."))

    try:
        result = ResultViewService(db).page_table(
            ServiceTablePageQuery(
                source=_table_source_ref(req),
                filters=_result_filters(req.filters),
                sort=_result_sorts(req.sort),
                search=req.search,
                page=req.page,
                page_size=req.pageSize,
                count_mode=req.countMode,
            )
        )
    except ResultViewError as e:
        raise _result_view_http_error(e)
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        logger.exception("Failed to execute table data view query")
        raise HTTPException(status_code=500, detail=public_error("EXECUTION_ERROR", e))

    return ResultPageResponse(
        columns=result.columns,
        rows=result.rows,
        page=result.page,
        pageSize=result.page_size,
        rowCount=result.row_count,
        hasNextPage=result.has_next_page,
        executedSql=result.executed_sql,
        latencyMs=result.latency_ms,
        warnings=result.warnings,
        notices=result.notices,
    )


@router.post("/agent/results/table/export")
def api_agent_table_result_export(req: TableResultExportRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    from engine.models import DataSource

    ds = db.query(DataSource).filter(DataSource.id == req.datasourceId).first()
    if not ds:
        raise HTTPException(status_code=404, detail=public_error("DATASOURCE_NOT_FOUND", "Datasource not found."))

    try:
        stream, _columns = ResultViewService(db).export_table_csv_stream(
            ServiceTableExportQuery(
                source=_table_source_ref(req),
                filters=_result_filters(req.filters),
                sort=_result_sorts(req.sort),
                search=req.search,
            )
        )
    except ResultViewError as e:
        raise _result_view_http_error(e)
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        logger.exception("Failed to export table data view query")
        raise HTTPException(status_code=500, detail=public_error("EXECUTION_ERROR", e))

    return StreamingResponse(
        stream,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="dbfox-table.csv"',
            "X-DBFox-Export-Max-Rows": str(export_max_rows_from_env()),
        },
    )


@router.post("/agent/results/export")
def api_agent_result_export(req: ResultExportRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    from engine.models import DataSource

    ds = db.query(DataSource).filter(DataSource.id == req.datasourceId).first()
    if not ds:
        raise HTTPException(status_code=404, detail=public_error("DATASOURCE_NOT_FOUND", "Datasource not found."))

    try:
        stream, _columns = ResultViewService(db).export_csv_stream(
            ServiceResultExportQuery(
                source=_result_source_ref(req),
                filters=_result_filters(req.filters),
                sort=_result_sorts(req.sort),
                search=req.search,
            )
        )
    except ResultViewError as e:
        raise _result_view_http_error(e)
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        logger.exception("Failed to export derived query")
        raise HTTPException(status_code=500, detail=public_error("EXECUTION_ERROR", e))

    return StreamingResponse(
        stream,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="dbfox-result.csv"',
            "X-DBFox-Export-Max-Rows": str(export_max_rows_from_env()),
        },
    )
