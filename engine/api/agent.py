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
from pydantic import BaseModel
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
from engine.db import get_db
from engine.errors import DBFoxError
from engine.llm.errors import llm_error_from_exception
from engine.llm.providers.openai import create_openai_client
from engine.models import AgentArtifactRecord, AgentRun

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
    key = (req.api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
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
        "error": message,
        "response": None,
        "code": code,
    }
    return f"event: agent.run.failed\ndata: {json.dumps(payload)}\n\n"


def _http_detail(exc: DBFoxError) -> dict[str, str]:
    from engine.policy.error_sanitizer import sanitize_error_message
    return {"code": exc.code, "message": sanitize_error_message(str(exc))}


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
            detail={"code": "AGENT_RUNTIME_ERROR", "message": f"Agent runtime failed: {str(exc)}"},
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
        from engine.policy.error_sanitizer import sanitized_http_detail
        raise HTTPException(status_code=400, detail=sanitized_http_detail(exc, exc.code))
    except Exception as exc:
        db.rollback()
        llm_error = llm_error_from_exception(exc)
        if llm_error is not None:
            raise HTTPException(status_code=400, detail=_http_detail(llm_error))
        logger.exception("Agent runtime resume failed")
        from engine.policy.error_sanitizer import sanitize_error_message
        raise HTTPException(
            status_code=500,
            detail={"code": "AGENT_RESUME_ERROR", "message": sanitize_error_message(f"Agent resume failed: {str(exc)}")},
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
            detail={"code": "AGENT_CANCEL_ERROR", "message": f"Failed to cancel run: {str(exc)}"},
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
        from engine.policy.error_sanitizer import sanitized_http_detail
        raise HTTPException(status_code=400, detail=sanitized_http_detail(exc, exc.code))
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to resolve agent approval")
        from engine.policy.error_sanitizer import sanitize_error_message
        raise HTTPException(
            status_code=500,
            detail={"code": "APPROVAL_RESOLVE_ERROR", "message": sanitize_error_message(f"Failed to resolve approval: {str(exc)}")},
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
    page: int
    pageSize: int
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

def _normalize_sql_for_source_match(sql: str) -> str:
    return " ".join(sql.strip().split())


def _artifact_payload(record: AgentArtifactRecord) -> dict[str, object]:
    try:
        payload = json.loads(record.payload_json or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_sql_from_artifact(record: AgentArtifactRecord) -> str:
    payload = _artifact_payload(record)
    for key in ("safeSql", "safe_sql", "sourceSql", "source_sql", "sql"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _result_columns_from_artifact(record: AgentArtifactRecord) -> set[str]:
    payload = _artifact_payload(record)
    raw_columns = payload.get("columns")
    if not isinstance(raw_columns, list):
        return set()

    columns: set[str] = set()
    for item in raw_columns:
        name = ""
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            raw_name = item.get("name") or item.get("field") or item.get("column")
            name = raw_name if isinstance(raw_name, str) else ""
        name = name.strip()
        if name:
            columns.add(_normalize_result_column_name(name))
    return columns


def _normalize_result_column_name(column: str) -> str:
    return column.strip().strip('`"[]').lower()


def _load_source_artifact(
    db: Session,
    *,
    datasource_id: str,
    source_artifact_id: str,
) -> AgentArtifactRecord | None:
    base_query = (
        db.query(AgentArtifactRecord)
        .join(AgentRun, AgentRun.id == AgentArtifactRecord.run_id)
        .filter(AgentRun.datasource_id == datasource_id)
    )
    by_id = base_query.filter(AgentArtifactRecord.id == source_artifact_id).first()
    if by_id is not None:
        return by_id
    return (
        base_query
        .filter(AgentArtifactRecord.semantic_id == source_artifact_id)
        .order_by(AgentArtifactRecord.created_at.desc())
        .first()
    )


def _verified_pagination_source(
    db: Session,
    req: ResultPageRequest,
    dialect: str,
) -> tuple[str, AgentArtifactRecord]:
    source = _load_source_artifact(
        db,
        datasource_id=req.datasourceId,
        source_artifact_id=req.sourceSqlArtifactId,
    )
    if source is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SOURCE_ARTIFACT_NOT_FOUND", "message": "Source result artifact was not found."},
        )
    if source.type not in {"result_view", "table", "sql"}:
        raise HTTPException(
            status_code=400,
            detail={"code": "SOURCE_ARTIFACT_UNSUPPORTED", "message": "Source artifact cannot back pagination."},
        )

    persisted_safe_sql = _safe_sql_from_artifact(source)
    if not persisted_safe_sql:
        raise HTTPException(
            status_code=400,
            detail={"code": "SOURCE_SQL_MISSING", "message": "Source artifact does not contain safe SQL."},
        )
    if _normalize_sql_for_source_match(persisted_safe_sql) != _normalize_sql_for_source_match(req.safeSql):
        raise HTTPException(
            status_code=400,
            detail={"code": "SOURCE_SQL_MISMATCH", "message": "Requested SQL does not match the source artifact."},
        )

    from engine.sql.safety_gate import validate_pagination_base_sql

    warnings = validate_pagination_base_sql(persisted_safe_sql, dialect=dialect)
    if warnings:
        raise HTTPException(
            status_code=400,
            detail={"code": "SOURCE_SQL_VALIDATION_FAILED", "message": warnings[0]},
        )
    return persisted_safe_sql, source


def _verified_pagination_source_sql(db: Session, req: ResultPageRequest, dialect: str) -> str:
    source_sql, _ = _verified_pagination_source(db, req, dialect)
    return source_sql


def _validated_result_page_sorts(
    req: ResultPageRequest,
    source: AgentArtifactRecord,
) -> list[dict[str, str]] | None:
    if not req.sort:
        return None

    allowed_columns = _result_columns_from_artifact(source)
    if not allowed_columns:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SOURCE_COLUMNS_MISSING",
                "message": "Source result artifact does not list sortable columns.",
            },
        )

    sorts: list[dict[str, str]] = []
    for sort in req.sort:
        normalized = _normalize_result_column_name(sort.column)
        if normalized not in allowed_columns:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "SORT_COLUMN_NOT_ALLOWED",
                    "message": f"Sort column '{sort.column}' is not present in the source result.",
                },
            )
        sorts.append({"column": sort.column.strip(), "direction": sort.direction})
    return sorts


def _pagination_execution_decision(datasource_id: str, original_sql: str, safe_sql: str):
    from engine.sql.trust_gate import ExecutionSafetyDecision

    guardrail = {
        "result": "pass",
        "originalSql": original_sql,
        "safeSql": safe_sql,
        "checks": [],
        "message": "Pagination derived from persisted safe SQL artifact.",
    }
    return ExecutionSafetyDecision(
        datasource_id=datasource_id,
        policy="readonly",
        original_sql=original_sql,
        safe_sql=safe_sql,
        passed=True,
        can_execute=True,
        requires_confirmation=False,
        guardrail=guardrail,
        schema_warnings=[],
        scope_state={"source": "pagination"},
        messages=[],
    )


def _build_result_view_sql(
    *,
    req: ResultPageRequest | ResultExportRequest,
    source_sql: str,
    source_artifact: AgentArtifactRecord,
    dialect: str,
    limit: int | None,
    offset: int | None,
) -> str:
    from engine.sql.sql_backed_view import (
        SqlBackedFilter,
        SqlBackedSort,
        SqlBackedViewError,
        build_sql_backed_page_sql,
    )

    source_columns = sorted(_result_columns_from_artifact(source_artifact))
    try:
        derived = build_sql_backed_page_sql(
            base_sql=source_sql,
            dialect=dialect,
            columns=source_columns,
            filters=[SqlBackedFilter.model_validate(item.model_dump()) for item in (req.filters or [])],
            search=req.search,
            searchable_columns=source_columns,
            sorts=[SqlBackedSort.model_validate(item.model_dump()) for item in (req.sort or [])],
            limit=limit,
            offset=offset,
        )
        return derived.sql
    except SqlBackedViewError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "DERIVED_SQL_BUILD_FAILED", "message": f"Failed to build derived SQL: {e}"},
        )


@router.post("/agent/results/page", response_model=ResultPageResponse)
def api_agent_result_page(req: ResultPageRequest, db: Session = Depends(get_db)) -> ResultPageResponse:
    from engine.sql.safety_gate import validate_derived_sql
    from engine.sql.executor import execute_query
    from engine.models import DataSource

    ds = db.query(DataSource).filter(DataSource.id == req.datasourceId).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found.")
        
    dialect = ds.db_type or "mysql"

    # Calculate limit and offset
    limit = req.pageSize
    offset = (req.page - 1) * req.pageSize

    source_sql, source_artifact = _verified_pagination_source(db, req, dialect)

    derived_sql = _build_result_view_sql(
        req=req,
        source_sql=source_sql,
        source_artifact=source_artifact,
        dialect=dialect,
        limit=limit + 1, # Fetch one extra to determine hasNextPage
        offset=offset,
    )

    warnings = validate_derived_sql(derived_sql, dialect=dialect)
    if warnings:
        raise HTTPException(status_code=400, detail={"code": "DERIVED_SQL_VALIDATION_FAILED", "message": warnings[0]})

    try:
        decision = _pagination_execution_decision(
            req.datasourceId,
            original_sql=source_sql,
            safe_sql=derived_sql,
        )
        res = execute_query(db, req.datasourceId, derived_sql, safety_decision=decision)
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        logger.exception("Failed to execute derived query")
        raise HTTPException(status_code=500, detail={"code": "EXECUTION_ERROR", "message": str(e)})

    rows = res.get("rows", [])
    has_next = len(rows) > limit
    returned_rows = rows[:limit]

    # Handle exact count if requested
    row_count = None
    if req.countMode == "exact":
        # build count query
        import sqlglot
        try:
            base_expr = sqlglot.parse_one(source_sql, read=dialect)
            count_sql = sqlglot.select("COUNT(*)").from_(base_expr.subquery("dbfox_count")).sql(dialect=dialect)
            
            count_decision = _pagination_execution_decision(
                req.datasourceId,
                original_sql=source_sql,
                safe_sql=count_sql,
            )
            count_res = execute_query(db, req.datasourceId, count_sql, safety_decision=count_decision)
            if count_res.get("rows") and len(count_res["rows"]) > 0:
                # Get first value of first row
                first_row = count_res["rows"][0]
                if first_row:
                    row_count = int(list(first_row.values())[0])
        except Exception as e:
            logger.warning(f"Failed to execute exact count query: {e}")

    return ResultPageResponse(
        columns=res.get("columns", []),
        rows=returned_rows,
        page=req.page,
        pageSize=req.pageSize,
        rowCount=row_count,
        hasNextPage=has_next,
        executedSql=derived_sql,
        latencyMs=res.get("latencyMs", 0),
        warnings=res.get("warnings"),
        notices=res.get("notices"),
    )


@router.post("/agent/results/export")
def api_agent_result_export(req: ResultExportRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    import csv
    import io

    from engine.sql.safety_gate import validate_derived_sql
    from engine.sql.executor import execute_query
    from engine.models import DataSource

    ds = db.query(DataSource).filter(DataSource.id == req.datasourceId).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found.")

    dialect = ds.db_type or "mysql"
    source_sql, source_artifact = _verified_pagination_source(db, req, dialect)
    derived_sql = _build_result_view_sql(
        req=req,
        source_sql=source_sql,
        source_artifact=source_artifact,
        dialect=dialect,
        limit=None,
        offset=None,
    )

    warnings = validate_derived_sql(derived_sql, dialect=dialect)
    if warnings:
        raise HTTPException(status_code=400, detail={"code": "DERIVED_SQL_VALIDATION_FAILED", "message": warnings[0]})

    try:
        decision = _pagination_execution_decision(
            req.datasourceId,
            original_sql=source_sql,
            safe_sql=derived_sql,
        )
        res = execute_query(db, req.datasourceId, derived_sql, safety_decision=decision)
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        logger.exception("Failed to export derived query")
        raise HTTPException(status_code=500, detail={"code": "EXECUTION_ERROR", "message": str(e)})

    columns = list(res.get("columns") or [])
    rows = list(res.get("rows") or [])

    def stream_csv():
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        stream_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="dbfox-result.csv"'},
    )
