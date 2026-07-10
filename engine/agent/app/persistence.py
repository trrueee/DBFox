from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ApprovalCheckpointDraft:
    response: AgentRunResponse
    approval: AgentApprovalRecord | None
    status: str
    current_step_name: str
    next_step_name: str | None
    plan: Any | None
    state: dict[str, Any]
    completed_steps: list[dict[str, Any]]
    pending_steps: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    waiting_approval_id: str | None


def resolve_session_id(db: Session, req: AgentRunRequest) -> str:
    """Resolve the session ID for the run, preserving multi-turn thread continuity."""
    if req.conversation_id:
        return str(req.conversation_id)
    if req.session_id:
        return str(req.session_id)
    if req.parent_run_id:
        parent = db.query(AgentRun).filter(AgentRun.id == req.parent_run_id).first()
        if parent is not None:
            return str(parent.session_id)
    if req.follow_up_context and req.follow_up_context.session_id:
        return str(req.follow_up_context.session_id)
    return str(uuid.uuid4())


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
        conversation_id=str(run.session_id),
        user_message_id=str(run.user_message_id) if run.user_message_id else None,
        assistant_message_id=str(run.assistant_message_id) if run.assistant_message_id else None,
        parent_run_id=str(run.parent_run_id) if run.parent_run_id else None,
        llm_credential_id=str(run.llm_credential_id) if run.llm_credential_id else None,
        api_base=str(run.api_base) if run.api_base else None,
        model_name=str(run.model_name) if run.model_name else None,
        execute=True,
        max_steps=20,
    )


def build_approval_checkpoint_draft(
    run_id: str,
    session_id: str,
    req: AgentRunRequest,
    full_state: dict[str, Any],
    steps: list[Any],
    artifacts: list[Any],
) -> ApprovalCheckpointDraft:
    """Build the approval checkpoint payload; persistence is owned by AgentEventStore."""
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

    return ApprovalCheckpointDraft(
        response=response,
        approval=approval,
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
        artifacts=_checkpoint_items(artifacts),
        waiting_approval_id=approval.id if approval else None,
    )


def _checkpoint_items(items: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in items:
        if hasattr(item, "model_dump"):
            value = item.model_dump(mode="json")
        elif isinstance(item, dict):
            value = dict(item)
        else:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records
