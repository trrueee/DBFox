"""Agent API Router — consolidated /agent/* entry points.

This module replaces the legacy engine/api/ai.py which mixed agent run routes
with old Text-to-SQL (/query/generate), golden-sql, and llm-logs endpoints.

Phase 1 (2026-06): All agent routes consolidated under /agent/*.
Old /query/agent-* paths are removed.
"""

from __future__ import annotations

import json
import logging
import os
import time as _time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.agent import DBFoxAgentRuntime
from engine.agent_core import persistence as agent_persistence
from engine.agent_core.types import (
    AgentApprovalDecisionRequest,
    AgentResumeRequest,
    AgentRunRequest,
    AgentRunResponse,
    AgentRuntimeEvent,
)
from engine.agent_core.events import EventEmitter
from engine.app.errors import public_error, public_message
from engine.db import get_db
from engine.errors import DBFoxError
from engine.llm.errors import llm_error_from_exception
from engine.llm.providers.openai import create_openai_client
from engine.sql.execution.streaming_executor import export_max_rows_from_env
from engine.sql.result_view.models import (
    ResultExportQuery as ServiceResultExportQuery,
    ResultFilter as ServiceResultFilter,
    ResultPageQuery as ServiceResultPageQuery,
    ResultSort as ServiceResultSort,
    ResultSourceRef,
    ResultViewError,
)
from engine.sql.result_view.service import ResultViewService

logger = logging.getLogger("dbfox.api.agent")
router = APIRouter()


class LlmTestRequest(BaseModel):
    api_key: str
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

    This endpoint validates that the provided api_key, api_base, and model_name
    can actually reach the target LLM service before the user attempts a full
    agent run.
    """
    t0 = _time.monotonic()
    try:
        client = create_openai_client(
            model_name=req.model_name,
            api_key=req.api_key,
            api_base=req.api_base,
            timeout=10.0,
            max_tokens=1,
        )
        # Minimal invocation to verify auth + connectivity + model existence.
        client.invoke("ping")
        latency_ms = int((_time.monotonic() - t0) * 1000)
        return LlmTestResponse(
            ok=True,
            model=req.model_name,
            api_base=req.api_base,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = int((_time.monotonic() - t0) * 1000)
        llm_error = llm_error_from_exception(exc)
        if llm_error is not None:
            return LlmTestResponse(
                ok=False,
                model=req.model_name,
                api_base=req.api_base,
                latency_ms=latency_ms,
                error_code=llm_error.code,
                error_message=str(llm_error),
            )
        return LlmTestResponse(
            ok=False,
            model=req.model_name,
            api_base=req.api_base,
            latency_ms=latency_ms,
            error_code="LLM_UNKNOWN_ERROR",
            error_message=f"{type(exc).__name__}: {exc}",
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _check_llm_credentials(req: AgentRunRequest) -> None:
    if os.environ.get("DBFOX_TESTING") == "1":
        # Test environment runs the agent against mocked LLM nodes.
        return
    key = str(req.api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise DBFoxError("请先在设置中配置 LLM API Key。", code="NO_LLM_KEY")


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


def sse_failed_event(event_id: str, run_id: str, message: str, code: str) -> str:
    """Build a formatted SSE error event string."""
    payload = {
        "event_id": event_id,
        "run_id": run_id,
        "sequence": 1,
        "created_at_ms": 0,
        "type": "agent.run.failed",
        "error": public_message(message),
        "response": None,
        "code": code,
    }
    return f"event: agent.run.failed\ndata: {json.dumps(payload)}\n\n"


def _http_detail(exc: DBFoxError) -> dict[str, str]:
    detail = public_error(exc.code, exc)
    return {"code": str(detail["code"]), "message": str(detail["message"])}


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
        _check_llm_credentials(req)
        return DBFoxAgentRuntime(db).run(req)
    except DBFoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=_http_detail(exc))
    except Exception as exc:
        db.rollback()
        llm_error = llm_error_from_exception(exc)
        if llm_error is not None:
            raise HTTPException(status_code=400, detail=_http_detail(llm_error))
        logger.exception("Agent runtime failed")
        raise HTTPException(
            status_code=500,
            detail=public_error("AGENT_RUNTIME_ERROR", f"Agent runtime failed: {str(exc)}"),
        )


@router.post("/agent/runs/{run_id}/resume", response_model=AgentRunResponse)
def api_agent_run_resume(
    run_id: str,
    req: AgentResumeRequest,
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    try:
        return DBFoxAgentRuntime(db).resume(run_id, req.approval_id)
    except DBFoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=public_error(exc.code, exc))
    except Exception as exc:
        db.rollback()
        llm_error = llm_error_from_exception(exc)
        if llm_error is not None:
            raise HTTPException(status_code=400, detail=_http_detail(llm_error))
        logger.exception("Agent runtime resume failed")
        raise HTTPException(
            status_code=500,
            detail=public_error("AGENT_RESUME_ERROR", f"Agent resume failed: {str(exc)}"),
        )


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
        logger.exception("Failed to cancel agent run %s", run_id)
        raise HTTPException(
            status_code=500,
            detail=public_error("AGENT_CANCEL_ERROR", f"Failed to cancel run: {str(exc)}"),
        )


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
        raise HTTPException(status_code=400, detail=public_error(exc.code, exc))
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to resolve agent approval")
        raise HTTPException(
            status_code=500,
            detail=public_error("APPROVAL_RESOLVE_ERROR", f"Failed to resolve approval: {str(exc)}"),
        )


# ---------------------------------------------------------------------------
# Agent run — SSE streaming routes
# ---------------------------------------------------------------------------

@router.post("/agent/run/stream")
def api_agent_run_stream(req: AgentRunRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    def stream_events() -> Any:  # noqa
        try:
            _check_llm_credentials(req)
            for event in DBFoxAgentRuntime(db).run_iter(req):
                attach_conversation_event_ids(event, req)
                yield _format_sse_event(event)
        except DBFoxError as exc:
            db.rollback()
            yield sse_failed_event("runtime_error_dbfox", "", str(exc), exc.code)
        except Exception as exc:
            db.rollback()
            llm_error = llm_error_from_exception(exc)
            if llm_error is not None:
                yield sse_failed_event("runtime_error_llm", "", str(llm_error), llm_error.code)
                return
            logger.exception("Agent runtime stream failed")
            yield sse_failed_event("runtime_error_unhandled", "", f"Agent runtime failed: {str(exc)}", "AGENT_RUNTIME_ERROR")

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
        except DBFoxError as exc:
            db.rollback()
            yield sse_failed_event("runtime_resume_error_dbfox", run_id, str(exc), exc.code)
        except Exception as exc:
            db.rollback()
            llm_error = llm_error_from_exception(exc)
            if llm_error is not None:
                yield sse_failed_event("runtime_resume_error_llm", run_id, str(llm_error), llm_error.code)
                return
            logger.exception("Agent runtime resume stream failed")
            yield sse_failed_event("runtime_resume_error_unhandled", run_id, f"Agent resume failed: {str(exc)}", "AGENT_RESUME_ERROR")

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

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
        raise HTTPException(status_code=404, detail="Datasource not found.")

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


@router.post("/agent/results/export")
def api_agent_result_export(req: ResultExportRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    from engine.models import DataSource

    ds = db.query(DataSource).filter(DataSource.id == req.datasourceId).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found.")

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
