"""Agent API Router — consolidated /agent/* entry points.

This module replaces the legacy engine/api/ai.py which mixed agent run routes
with old Text-to-SQL (/query/generate), golden-sql, and llm-logs endpoints.

Phase 1 (2026-06): All agent routes consolidated under /agent/*.
Old /query/agent-* paths are removed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from engine.agent import DataBoxAgentRuntime
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
from engine.errors import DataBoxError

logger = logging.getLogger("databox.api.agent")
router = APIRouter()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _format_sse_event(event: AgentRuntimeEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


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
        return DataBoxAgentRuntime(db).run(req)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
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
        return DataBoxAgentRuntime(db).resume(run_id, req.approval_id)
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()
        logger.exception("Agent runtime resume failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "AGENT_RESUME_ERROR", "message": f"Agent resume failed: {str(exc)}"},
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
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to resolve agent approval")
        raise HTTPException(
            status_code=500,
            detail={"code": "APPROVAL_RESOLVE_ERROR", "message": f"Failed to resolve approval: {str(exc)}"},
        )


# ---------------------------------------------------------------------------
# Agent run — SSE streaming routes
# ---------------------------------------------------------------------------

@router.post("/agent/run/stream")
def api_agent_run_stream(req: AgentRunRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    def stream_events() -> Any:  # noqa
        try:
            for event in DataBoxAgentRuntime(db).run_iter(req):
                yield _format_sse_event(event)
        except DataBoxError as exc:
            payload = {
                "event_id": "runtime_error_databox",
                "run_id": "",
                "sequence": 1,
                "created_at_ms": 0,
                "type": "agent.run.failed",
                "error": str(exc),
                "response": None,
                "code": exc.code,
            }
            yield f"event: agent.run.failed\ndata: {json.dumps(payload)}\n\n"
        except Exception as exc:
            logger.exception("Agent runtime stream failed")
            payload = {
                "event_id": "runtime_error_unhandled",
                "run_id": "",
                "sequence": 1,
                "created_at_ms": 0,
                "type": "agent.run.failed",
                "error": f"Agent runtime failed: {str(exc)}",
                "response": None,
                "code": "AGENT_RUNTIME_ERROR",
            }
            yield f"event: agent.run.failed\ndata: {json.dumps(payload)}\n\n"

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
            for event in DataBoxAgentRuntime(db).resume_iter(run_id, req.approval_id):
                yield _format_sse_event(event)
        except DataBoxError as exc:
            payload = {
                "event_id": "runtime_resume_error_databox",
                "run_id": run_id,
                "sequence": 1,
                "created_at_ms": 0,
                "type": "agent.run.failed",
                "error": str(exc),
                "response": None,
                "code": exc.code,
            }
            yield f"event: agent.run.failed\ndata: {json.dumps(payload)}\n\n"
        except Exception as exc:
            logger.exception("Agent runtime resume stream failed")
            payload = {
                "event_id": "runtime_resume_error_unhandled",
                "run_id": run_id,
                "sequence": 1,
                "created_at_ms": 0,
                "type": "agent.run.failed",
                "error": f"Agent resume failed: {str(exc)}",
                "response": None,
                "code": "AGENT_RESUME_ERROR",
            }
            yield f"event: agent.run.failed\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
