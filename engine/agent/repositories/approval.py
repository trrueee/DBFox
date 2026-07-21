"""Approval request and exactly-once resolution transactions."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.approval import Approval, ApprovalConflict, ApprovalStatus
from engine.agent.events import RuntimeEventProjector, RuntimeEventType
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.observation import ObservationStatus
from engine.agent.run import RunStatus
from engine.agent.session import SessionLease
from engine.agent.tool import ToolInvocationStatus
from engine.models import AgentApproval, AgentRun, AgentSessionInput, AgentToolInvocation
from engine.security.audit import SecurityAuditService


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ApprovalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sessions = SessionRepository(session)

    def request(
        self,
        *,
        lease: SessionLease,
        invocation_id: str,
        policy_decision: dict[str, Any],
        expires_in_seconds: int = 3600,
    ) -> Approval:
        begin_agent_write(self.session)
        invocation = self.session.execute(
            select(AgentToolInvocation).where(AgentToolInvocation.id == invocation_id).with_for_update()
        ).scalar_one()
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == invocation.run_id).with_for_update()
        ).scalar_one()
        if str(run.session_id) != lease.session_id or int(run.lease_token or 0) != lease.token:
            raise ApprovalConflict("Approval request is fenced by another Session owner")
        if invocation.status != ToolInvocationStatus.WAITING_APPROVAL.value:
            raise ApprovalConflict(f"Invocation cannot request approval from {invocation.status}")
        existing = self.session.execute(
            select(AgentApproval).where(AgentApproval.tool_invocation_id == invocation_id)
        ).scalar_one_or_none()
        if existing is not None:
            return self._domain(existing)
        now = _utcnow()
        row = AgentApproval(
            id=f"approval_{uuid4().hex}", run_id=str(run.id), session_id=str(run.session_id),
            step_name="tool_execution", tool_name=str(invocation.tool_name),
            turn_id=str(invocation.turn_id), tool_invocation_id=str(invocation.id),
            status=ApprovalStatus.PENDING.value, version=0,
            risk_level=str(policy_decision.get("risk_level") or "warning"),
            reason=str(policy_decision.get("reason") or "This action requires approval."),
            policy_decision_json=_json(policy_decision),
            requested_action_json=_json({
                "tool_name": str(invocation.tool_name),
                "arguments": policy_decision.get("safe_args") or {},
            }),
            created_at=now, expires_at=now + timedelta(seconds=expires_in_seconds),
        )
        self.session.add(row)
        self.session.flush()
        invocation.approval_id = row.id
        run.status = RunStatus.WAITING_APPROVAL.value
        run.version = int(run.version or 0) + 1
        run.updated_at = now
        value = self._domain(row)
        self.sessions.append_event(
            lease=lease, event_type=RuntimeEventType.APPROVAL_REQUESTED,
            run_id=str(run.id), turn_id=str(invocation.turn_id),
            payload=RuntimeEventProjector.entity("approval", value),
        )
        SecurityAuditService(self.session).record(
            action="agent.approval.request",
            outcome="requested",
            resource_type="tool_invocation",
            resource_id=str(invocation.id),
            session_id=str(run.session_id),
            run_id=str(run.id),
            correlation_id=str(row.id),
            details={"tool_name": str(invocation.tool_name), "risk_level": str(row.risk_level)},
        )
        return value

    def was_rejected_without_new_input(
        self,
        *,
        run_id: str,
        tool_name: str,
        input_hash: str,
    ) -> bool:
        """Return whether the exact action was denied and the user has not redirected the Run.

        Approval is an authorization boundary, not a retryable tool error. A model
        therefore cannot obtain a fresh prompt for the same action merely by
        emitting another provider call id. A formally admitted steer input is the
        only in-Run signal that may supersede the prior decision.
        """
        rejected_at = self.session.execute(
            select(AgentApproval.decided_at)
            .join(
                AgentToolInvocation,
                AgentToolInvocation.id == AgentApproval.tool_invocation_id,
            )
            .where(
                AgentApproval.run_id == run_id,
                AgentApproval.status == ApprovalStatus.REJECTED.value,
                AgentToolInvocation.tool_name == tool_name,
                AgentToolInvocation.input_hash == input_hash,
            )
            .order_by(AgentApproval.decided_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if rejected_at is None:
            return False
        redirected = self.session.execute(
            select(AgentSessionInput.id)
            .where(
                AgentSessionInput.run_id == run_id,
                AgentSessionInput.admitted_at > rejected_at,
            )
            .limit(1)
        ).scalar_one_or_none()
        return redirected is None

    def resolve(
        self,
        *,
        approval_id: str,
        expected_version: int,
        approved: bool,
        actor: str,
        note: str | None = None,
    ) -> Approval:
        begin_agent_write(self.session)
        row = self.session.execute(
            select(AgentApproval).where(AgentApproval.id == approval_id).with_for_update()
        ).scalar_one()
        if row.status != ApprovalStatus.PENDING.value or int(row.version or 0) != expected_version:
            raise ApprovalConflict("Approval has already changed")
        now = _utcnow()
        expires_at = row.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        invocation = self.session.execute(
            select(AgentToolInvocation).where(
                AgentToolInvocation.id == row.tool_invocation_id
            ).with_for_update()
        ).scalar_one()
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == row.run_id).with_for_update()
        ).scalar_one()
        lease = self.sessions.claim(session_id=str(run.session_id), owner=f"approval:{approval_id}")
        if lease is None:
            raise ApprovalConflict("Session is currently owned; retry approval resolution")
        run.lease_token = lease.token
        if expires_at is not None and expires_at <= now:
            row.status = ApprovalStatus.EXPIRED.value
            invocation.status = ToolInvocationStatus.REJECTED.value
        elif approved:
            row.status = ApprovalStatus.APPROVED.value
            invocation.status = ToolInvocationStatus.REQUESTED.value
            run.status = RunStatus.RUNNING.value
        else:
            row.status = ApprovalStatus.REJECTED.value
            invocation.status = ToolInvocationStatus.REJECTED.value
            run.status = RunStatus.RUNNING.value
        row.version = int(row.version or 0) + 1
        row.decided_at = now
        row.consumed_at = now
        row.decided_by = actor
        row.decision_note = note
        run.version = int(run.version or 0) + 1
        run.updated_at = now
        self.session.flush()
        if row.status in {ApprovalStatus.REJECTED.value, ApprovalStatus.EXPIRED.value}:
            ToolInvocationRepository(self.session).settle(
                lease=lease,
                invocation_id=str(invocation.id),
                status=ObservationStatus.REJECTED,
                model_visible_summary=(
                    "The requested action expired before approval."
                    if row.status == ApprovalStatus.EXPIRED.value
                    else "The user rejected the requested action. Continue without it or explain the limitation."
                ),
                error_code=(
                    "APPROVAL_EXPIRED"
                    if row.status == ApprovalStatus.EXPIRED.value
                    else "APPROVAL_REJECTED"
                ),
                error_message="The requested action was not authorized.",
            )
        self.sessions.append_event(
            lease=lease, event_type=RuntimeEventType.APPROVAL_RESOLVED,
            run_id=str(run.id), turn_id=str(invocation.turn_id),
            payload=RuntimeEventProjector.entity("approval", self._domain(row)),
        )
        value = self._domain(row)
        SecurityAuditService(self.session).record(
            action="agent.approval.resolve",
            outcome="allowed" if row.status == ApprovalStatus.APPROVED.value else "denied",
            resource_type="tool_invocation",
            resource_id=str(invocation.id),
            session_id=str(run.session_id),
            run_id=str(run.id),
            actor_id=actor,
            correlation_id=str(row.id),
            details={"tool_name": str(invocation.tool_name), "decision_status": str(row.status)},
        )
        self.sessions.release(lease=lease)
        return value

    @staticmethod
    def _domain(row: AgentApproval) -> Approval:
        return Approval(
            id=str(row.id), session_id=str(row.session_id), run_id=str(row.run_id),
            turn_id=str(row.turn_id), tool_invocation_id=str(row.tool_invocation_id),
            tool_name=str(row.tool_name), status=ApprovalStatus(str(row.status)),
            version=int(row.version or 0), risk_level=str(row.risk_level),
            reason=str(row.reason or ""),
            policy_decision=json.loads(str(row.policy_decision_json or "{}")),
            requested_action=json.loads(str(row.requested_action_json or "{}")),
            created_at=row.created_at,
            expires_at=row.expires_at,
            decided_at=row.decided_at,
            decided_by=str(row.decided_by) if row.decided_by else None,
            decision_note=str(row.decision_note) if row.decision_note else None,
        )
