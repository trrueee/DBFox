from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from engine.errors import DBFoxError
from engine.models import AgentRun
from engine.agent_core import persistence as agent_persistence
from engine.agent_core.types import (
    AgentApprovalRecord,
    AgentCheckpointRecord,
    AgentRunRequest,
    AgentRunResponse,
)
from engine.agent.app.response_builder import build_response

logger = logging.getLogger("dbfox.dbfox_agent.app.persistence")


def resolve_session_id(db: Session, req: AgentRunRequest) -> str:
    """Resolve the session ID for the run, preserving multi-turn thread continuity."""
    if req.session_id:
        return str(req.session_id)
    if req.parent_run_id:
        parent = db.query(AgentRun).filter(AgentRun.id == req.parent_run_id).first()
        if parent is not None:
            return str(parent.session_id)
    if req.follow_up_context and req.follow_up_context.session_id:
        return str(req.follow_up_context.session_id)
    return str(uuid.uuid4())


def start_run_persistence(persistence_sink: Any, req: AgentRunRequest, run_id: str, session_id: str, db: Session) -> None:
    """Initialize persist logging for the agent execution session."""
    try:
        persistence_sink.init_run_session(req, run_id, session_id)
    except Exception as exc:
        logger.warning("Failed to start persistence for run %s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass


def pending_approval_from_workspace(db: Session, req: AgentRunRequest) -> dict[str, Any] | None:
    """Extract pending approval details from the workspace context."""
    workspace = req.workspace_context
    approval_id = getattr(workspace, "pending_approval_id", None) if workspace else None
    if not approval_id:
        return None
    approval = agent_persistence.get_approval(db, str(approval_id))
    if approval is None or approval.status != "pending":
        return None
    return approval.model_dump(mode="json")


def request_from_run(db: Session, run_id: str) -> AgentRunRequest:
    """Reconstruct an AgentRunRequest from an existing run record in the database."""
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run is None:
        raise DBFoxError("Agent run not found.", code="RUN_NOT_FOUND")
    return AgentRunRequest(
        datasource_id=str(run.datasource_id),
        question=str(run.question),
        session_id=str(run.session_id),
        parent_run_id=str(run.parent_run_id) if run.parent_run_id else None,
        execute=True,
        max_steps=run.max_steps if run.max_steps else 20,
    )


def save_approval_checkpoint(
    db: Session,
    run_id: str,
    session_id: str,
    req: AgentRunRequest,
    full_state: dict[str, Any],
    steps: list[Any],
    artifacts: list[Any],
) -> tuple[AgentRunResponse, AgentApprovalRecord | None]:
    """Save an interrupt/approval checkpoint to the database."""
    pending = full_state.get("pending_approval") or {}
    approval = AgentApprovalRecord.model_validate(pending) if isinstance(pending, dict) else None

    # Build response first (without checkpoint) to get the steps mapped from trace_events
    response = build_response(
        req=req,
        run_id=run_id,
        session_id=session_id,
        state=full_state,
        steps=steps,
        artifacts=artifacts,
        success=False,
        error=None,
        status="waiting_approval",
        approval=approval,
        checkpoint=None,
    )

    current_step = response.steps[-1].name if (response.steps and len(response.steps) > 0) else "approval_interrupt"
    next_step = approval.step_name if approval else str(pending.get("tool_name", ""))

    checkpoint = agent_persistence.save_checkpoint(
        db,
        run_id=run_id,
        session_id=session_id,
        status="waiting_approval",
        current_step_name=current_step,
        next_step_name=next_step,
        plan=full_state.get("plan"),
        state=dict(full_state),
        completed_steps=[s.model_dump(mode="json") for s in response.steps],
        pending_steps=[
            {
                "name": pending.get("tool_name", ""),
                "tool_name": pending.get("tool_name"),
                "args": (pending.get("requested_action") or {}).get("args", {}),
            }
        ],
    )

    response.checkpoint = checkpoint

    try:
        if approval:
            agent_persistence.mark_run_waiting_approval(
                db,
                run_id=run_id,
                approval_id=approval.id,
                current_step_name=approval.step_name,
            )
        db.commit()
    except Exception as exc:
        logger.warning("Failed to persist waiting approval state for run %s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass

    return response, approval
