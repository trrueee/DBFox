"""Approval request and exactly-once resolution transactions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.approval import Approval, ApprovalConflict, ApprovalStatus
from engine.agent.events import RuntimeEventType
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.observation import ObservationStatus
from engine.agent.run import RunStatus
from engine.agent.run_item import approval_item, dump_run_item, project_run
from engine.agent.session import SessionLease
from engine.agent.tool import ToolInvocationStatus
from engine.json_codec import canonical_dumps as _json, loads
from engine.models import AgentApproval, AgentRun, AgentSessionInput, AgentToolInvocation
from engine.security.audit import SecurityAuditService


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
        self.sessions.events.append(
            lease=lease, event_type=RuntimeEventType.RUN_UPDATED,
            run_id=str(run.id), turn_id=str(invocation.turn_id),
            payload={"run": project_run(run)},
        )
        self.sessions.events.append(
            lease=lease, event_type=RuntimeEventType.RUN_ITEM_STARTED,
            run_id=str(run.id), turn_id=str(invocation.turn_id),
            payload={"item": dump_run_item(approval_item(row))},
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

    def expire_pending(
        self,
        *,
        lease: SessionLease,
        now: datetime | None = None,
    ) -> list[Approval]:
        """Settle every expired approval in the claimed Session.

        Expiration is a durable authorization decision. It must release the Run
        from ``waiting_approval`` and create the same model-visible observation
        as an explicit rejection so the next Turn can choose a safe alternative.
        """
        begin_agent_write(self.session)
        self.sessions.require_lease(lease=lease)
        current_time = now or _utcnow()
        rows = self.session.execute(
            select(AgentApproval).where(
                AgentApproval.session_id == lease.session_id,
                AgentApproval.status == ApprovalStatus.PENDING.value,
                AgentApproval.expires_at.is_not(None),
                AgentApproval.expires_at <= current_time,
            ).with_for_update()
        ).scalars().all()
        expired: list[Approval] = []
        for row in rows:
            invocation = self.session.execute(
                select(AgentToolInvocation).where(
                    AgentToolInvocation.id == row.tool_invocation_id
                ).with_for_update()
            ).scalar_one()
            run = self.session.execute(
                select(AgentRun).where(AgentRun.id == row.run_id).with_for_update()
            ).scalar_one()
            if run.status != RunStatus.WAITING_APPROVAL.value:
                continue
            run.lease_token = lease.token
            row.status = ApprovalStatus.EXPIRED.value
            row.version = int(row.version or 0) + 1
            row.decided_at = current_time
            row.consumed_at = current_time
            row.decided_by = "system:expiry"
            invocation.status = ToolInvocationStatus.REJECTED.value
            run.status = RunStatus.RUNNING.value
            run.version = int(run.version or 0) + 1
            run.updated_at = current_time
            self.session.flush()
            ToolInvocationRepository(self.session).settle(
                lease=lease,
                invocation_id=str(invocation.id),
                status=ObservationStatus.REJECTED,
                model_visible_summary="The requested action expired before approval.",
                error_code="APPROVAL_EXPIRED",
                error_message="The requested action was not authorized.",
            )
            value = self._domain(row)
            self.sessions.events.append(
                lease=lease,
                event_type=RuntimeEventType.RUN_ITEM_CANCELLED,
                run_id=str(run.id),
                turn_id=str(invocation.turn_id),
                payload={"item": dump_run_item(approval_item(row))},
            )
            self.sessions.events.append(
                lease=lease,
                event_type=RuntimeEventType.RUN_UPDATED,
                run_id=str(run.id),
                turn_id=str(invocation.turn_id),
                payload={"run": project_run(run)},
            )
            SecurityAuditService(self.session).record(
                action="agent.approval.resolve",
                outcome="denied",
                resource_type="tool_invocation",
                resource_id=str(invocation.id),
                session_id=str(run.session_id),
                run_id=str(run.id),
                actor_id="system:expiry",
                correlation_id=str(row.id),
                details={
                    "tool_name": str(invocation.tool_name),
                    "decision_status": ApprovalStatus.EXPIRED.value,
                },
            )
            expired.append(value)
        return expired

    def cancel_pending_for_run(
        self,
        *,
        lease: SessionLease,
        run_id: str,
    ) -> list[Approval]:
        """Terminalize unresolved approvals without reviving the cancelled Run."""
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        if str(run.session_id) != lease.session_id or int(run.lease_token or 0) != lease.token:
            raise ApprovalConflict("Approval cancellation is fenced by another Session owner")
        rows = self.session.execute(
            select(AgentApproval).where(
                AgentApproval.run_id == run_id,
                AgentApproval.status == ApprovalStatus.PENDING.value,
            ).with_for_update()
        ).scalars().all()
        now = _utcnow()
        cancelled: list[Approval] = []
        for row in rows:
            row.status = ApprovalStatus.CANCELLED.value
            row.version = int(row.version or 0) + 1
            row.decided_at = now
            row.consumed_at = now
            row.decided_by = "system:run_cancel"
            row.decision_note = "The Run was cancelled before this action was approved."
            self.session.flush()
            value = self._domain(row)
            self.sessions.events.append(
                lease=lease,
                event_type=RuntimeEventType.RUN_ITEM_CANCELLED,
                run_id=run_id,
                turn_id=str(row.turn_id),
                payload={"item": dump_run_item(approval_item(row))},
            )
            SecurityAuditService(self.session).record(
                action="agent.approval.resolve",
                outcome="cancelled",
                resource_type="tool_invocation",
                resource_id=str(row.tool_invocation_id),
                session_id=str(run.session_id),
                run_id=run_id,
                actor_id="system:run_cancel",
                correlation_id=str(row.id),
                details={
                    "tool_name": str(row.tool_name),
                    "decision_status": ApprovalStatus.CANCELLED.value,
                },
            )
            cancelled.append(value)
        return cancelled

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
        if run.status != RunStatus.WAITING_APPROVAL.value:
            raise ApprovalConflict(f"Approval cannot be resolved while Run is {run.status}")
        lease = self.sessions.claim(session_id=str(run.session_id), owner=f"approval:{approval_id}")
        if lease is None:
            raise ApprovalConflict("Session is currently owned; retry approval resolution")
        run.lease_token = lease.token
        if expires_at is not None and expires_at <= now:
            row.status = ApprovalStatus.EXPIRED.value
            invocation.status = ToolInvocationStatus.REJECTED.value
            run.status = RunStatus.RUNNING.value
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
        self.sessions.events.append(
            lease=lease,
            event_type=(
                RuntimeEventType.RUN_ITEM_CANCELLED
                if row.status == ApprovalStatus.EXPIRED.value
                else RuntimeEventType.RUN_ITEM_COMPLETED
            ),
            run_id=str(run.id), turn_id=str(invocation.turn_id),
            payload={"item": dump_run_item(approval_item(row))},
        )
        self.sessions.events.append(
            lease=lease, event_type=RuntimeEventType.RUN_UPDATED,
            run_id=str(run.id), turn_id=str(invocation.turn_id),
            payload={"run": project_run(run)},
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
            policy_decision=loads(str(row.policy_decision_json or "{}")),
            requested_action=loads(str(row.requested_action_json or "{}")),
            created_at=row.created_at,
            expires_at=row.expires_at,
            decided_at=row.decided_at,
            decided_by=str(row.decided_by) if row.decided_by else None,
            decision_note=str(row.decision_note) if row.decision_note else None,
        )
