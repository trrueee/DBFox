"""Approval lifecycle — create, get, list, resolve, expire."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from engine.errors import DBFoxError
from engine.agent_core.types import AgentApprovalRecord
from engine.models import AgentApproval, AgentRun
from engine.agent_core.persistence._common import (
    _safe_json,
    _approval_record,
    _normalize_risk_level,
    _parse_json,
)

logger = logging.getLogger("dbfox.agent.persistence")


def create_approval(
    db: Session,
    *,
    run_id: str,
    session_id: str,
    step_name: str,
    tool_name: str | None,
    risk_level: str,
    reason: str | None,
    policy_decision: dict[str, Any],
    requested_action: dict[str, Any] | None = None,
    expires_at: datetime | None = None,
) -> AgentApprovalRecord:
    approval = AgentApproval(
        id=f"approval_{uuid.uuid4().hex}",
        run_id=run_id,
        session_id=session_id,
        step_name=step_name,
        tool_name=tool_name,
        status="pending",
        risk_level=_normalize_risk_level(risk_level),
        reason=reason,
        policy_decision_json=_safe_json(policy_decision),
        requested_action_json=_safe_json(requested_action) if requested_action is not None else None,
        created_at=datetime.now(UTC),
        expires_at=expires_at,
    )
    db.add(approval)
    db.flush()
    return _approval_record(approval)


def get_approval(db: Session, approval_id: str) -> AgentApprovalRecord | None:
    approval = db.query(AgentApproval).filter(AgentApproval.id == approval_id).first()
    return _approval_record(approval) if approval is not None else None


def get_pending_approval_for_run(db: Session, run_id: str) -> AgentApprovalRecord | None:
    approval = (
        db.query(AgentApproval)
        .filter(AgentApproval.run_id == run_id, AgentApproval.status == "pending")
        .order_by(AgentApproval.created_at.desc())
        .first()
    )
    return _approval_record(approval) if approval is not None else None


def list_run_approvals(db: Session, run_id: str) -> list[AgentApprovalRecord]:
    approvals = (
        db.query(AgentApproval)
        .filter(AgentApproval.run_id == run_id)
        .order_by(AgentApproval.created_at.asc())
        .all()
    )
    return [_approval_record(approval) for approval in approvals]


def resolve_approval(
    db: Session,
    *,
    run_id: str,
    approval_id: str,
    decision: str,
    note: str | None = None,
    decided_by: str | None = "local-user",
) -> AgentApprovalRecord:
    if decision not in {"approved", "rejected"}:
        raise DBFoxError("Invalid approval decision.", code="INVALID_APPROVAL_DECISION")

    approval = db.query(AgentApproval).filter(AgentApproval.id == approval_id).first()
    if approval is None:
        raise DBFoxError("Approval not found.", code="APPROVAL_NOT_FOUND")
    if approval.run_id != run_id:
        raise DBFoxError("Approval does not belong to this run.", code="APPROVAL_RUN_MISMATCH")
    if approval.status != "pending":
        raise DBFoxError("Approval has already been resolved.", code="APPROVAL_ALREADY_RESOLVED")

    approval.status = decision  # type: ignore[assignment]
    approval.decided_by = decided_by  # type: ignore[assignment]
    approval.decision_note = note  # type: ignore[assignment]
    approval.decided_at = datetime.now(UTC)  # type: ignore[assignment]

    if decision == "rejected":
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run is not None:
            run.status = "failed"  # type: ignore[assignment]
            run.error = "Approval rejected"  # type: ignore[assignment]
            run.current_step_name = None  # type: ignore[assignment]
            run.waiting_approval_id = None  # type: ignore[assignment]
            run.completed_at = datetime.now(UTC)  # type: ignore[assignment]
            run.updated_at = datetime.now(UTC)  # type: ignore[assignment]

    db.flush()
    return _approval_record(approval)


def expire_approval(
    db: Session,
    *,
    approval_id: str,
    note: str,
    decided_by: str | None = "agent-kernel",
) -> AgentApprovalRecord | None:
    approval = db.query(AgentApproval).filter(AgentApproval.id == approval_id).first()
    if approval is None:
        return None
    if approval.status != "pending":
        return _approval_record(approval)

    approval.status = "expired"  # type: ignore[assignment]
    approval.decided_by = decided_by  # type: ignore[assignment]
    approval.decision_note = note  # type: ignore[assignment]
    approval.decided_at = datetime.now(UTC)  # type: ignore[assignment]

    run = db.query(AgentRun).filter(AgentRun.id == approval.run_id).first()
    if run is not None and run.waiting_approval_id == approval.id:
        run.waiting_approval_id = None  # type: ignore[assignment]
        run.current_step_name = None  # type: ignore[assignment]
        run.updated_at = datetime.now(UTC)  # type: ignore[assignment]

    db.flush()
    return _approval_record(approval)
