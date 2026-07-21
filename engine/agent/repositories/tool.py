"""Durable ToolInvocation intent and settlement repository."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.agent.events import RuntimeEventType
from engine.agent.observation import Observation, ObservationStatus
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.session import SessionLease
from engine.agent.tool import ToolInvocation, ToolInvocationStatus
from engine.models import AgentObservationRecord, AgentToolInvocation, AgentTurn
from engine.tools.materialization import ToolMaterialization
from engine.tools.materialization import ToolRecoveryPolicy


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class ToolInvocationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sessions = SessionRepository(session)

    def request(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        provider_call_id: str,
        tool_name: str,
        raw_input: dict[str, Any],
        materialization: ToolMaterialization,
        policy_decision: dict[str, Any],
    ) -> ToolInvocation:
        begin_agent_write(self.session)
        tool = materialization.require(tool_name)
        turn = self.session.get(AgentTurn, turn_id)
        if turn is None or str(turn.run_id) != run_id or str(turn.session_id) != lease.session_id:
            raise ValueError("Tool call is outside the active Turn")
        if str(turn.tool_materialization_hash) != materialization.hash:
            raise ValueError("Tool materialization does not match the frozen Turn snapshot")

        existing = self.session.execute(
            select(AgentToolInvocation).where(
                AgentToolInvocation.turn_id == turn_id,
                AgentToolInvocation.provider_call_id == provider_call_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return self._domain(existing)

        authorized_input = policy_decision.get("safe_args")
        if not isinstance(authorized_input, dict):
            authorized_input = {}
        authorized_input_hash = _hash(authorized_input)
        idempotency_key = _hash(
            {
                "run_id": run_id,
                "turn_id": turn_id,
                "provider_call_id": provider_call_id,
                "tool": tool.name,
                "version": tool.version,
                "authorized_input_hash": authorized_input_hash,
            }
        )
        policy_status = str(policy_decision.get("status") or "blocked")
        if policy_status == "blocked":
            status = ToolInvocationStatus.REJECTED
        elif policy_status == "approval_required":
            status = ToolInvocationStatus.WAITING_APPROVAL
        else:
            status = ToolInvocationStatus.REQUESTED
        row = AgentToolInvocation(
            id=f"invocation_{uuid4().hex}",
            session_id=lease.session_id,
            run_id=run_id,
            turn_id=turn_id,
            provider_call_id=provider_call_id,
            tool_name=tool.name,
            tool_version=tool.version,
            # The durable invocation is the action the policy authorized, not
            # the provider's untrusted request. Approval and leaf execution
            # therefore bind to exactly the same canonical input.
            input_json=_json(authorized_input),
            input_hash=authorized_input_hash,
            idempotency_key=idempotency_key,
            status=status.value,
            policy_json=_json(policy_decision),
            recovery_policy=tool.recovery_policy.value,
            attempt_count=0,
            created_at=_utcnow(),
        )
        self.session.add(row)
        self.session.flush()
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.TOOL_REQUESTED,
            run_id=run_id,
            turn_id=turn_id,
            payload={"tool_invocation": self._domain(row).model_dump(mode="json")},
        )
        return self._domain(row)

    def mark_running(self, *, lease: SessionLease, invocation_id: str) -> ToolInvocation:
        begin_agent_write(self.session)
        row = self.session.execute(
            select(AgentToolInvocation).where(AgentToolInvocation.id == invocation_id).with_for_update()
        ).scalar_one()
        if row.session_id != lease.session_id:
            raise ValueError("ToolInvocation is outside the Session")
        if row.status != ToolInvocationStatus.REQUESTED.value:
            raise ValueError(f"ToolInvocation cannot run from status {row.status}")
        row.status = ToolInvocationStatus.RUNNING.value
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.started_at = _utcnow()
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.TOOL_RUNNING,
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            payload={"tool_invocation_id": row.id, "attempt": row.attempt_count},
        )
        self.session.flush()
        return self._domain(row)

    def record_retry(self, *, lease: SessionLease, invocation_id: str) -> ToolInvocation:
        begin_agent_write(self.session)
        row = self.session.execute(
            select(AgentToolInvocation).where(AgentToolInvocation.id == invocation_id).with_for_update()
        ).scalar_one()
        if row.session_id != lease.session_id:
            raise ValueError("ToolInvocation is outside the Session")
        if row.status != ToolInvocationStatus.RUNNING.value:
            raise ValueError(f"ToolInvocation cannot retry from status {row.status}")
        row.attempt_count = int(row.attempt_count or 0) + 1
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.ACTIVITY_UPDATED,
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            payload={"activity": {
                "id": f"activity:{row.id}",
                "kind": "recovery",
                "title": "正在重试工具操作",
                "summary": f"第 {row.attempt_count} 次执行使用同一幂等调用标识。",
                "status": "running",
                "tool_invocation_id": str(row.id),
            }},
        )
        self.session.flush()
        return self._domain(row)

    def requested_for_run(self, run_id: str) -> list[ToolInvocation]:
        rows = self.session.execute(
            select(AgentToolInvocation).where(
                AgentToolInvocation.run_id == run_id,
                AgentToolInvocation.status == ToolInvocationStatus.REQUESTED.value,
            ).order_by(AgentToolInvocation.created_at)
        ).scalars()
        return [self._domain(row) for row in rows]

    def recover_interrupted(self, *, lease: SessionLease, run_id: str) -> list[ToolInvocation]:
        """Settle or requeue invocations left running by a crashed worker."""
        begin_agent_write(self.session)
        rows = self.session.execute(
            select(AgentToolInvocation).where(
                AgentToolInvocation.run_id == run_id,
                AgentToolInvocation.status == ToolInvocationStatus.RUNNING.value,
            ).order_by(AgentToolInvocation.created_at).with_for_update()
        ).scalars().all()
        retryable: list[ToolInvocation] = []
        for row in rows:
            if str(row.session_id) != lease.session_id:
                raise ValueError("ToolInvocation is outside the Session")
            policy = ToolRecoveryPolicy(str(row.recovery_policy))
            if policy is ToolRecoveryPolicy.RETRY_SAFE:
                row.status = ToolInvocationStatus.REQUESTED.value
                row.started_at = None
                self.sessions.append_event(
                    lease=lease,
                    event_type=RuntimeEventType.ACTIVITY_UPDATED,
                    run_id=run_id,
                    turn_id=str(row.turn_id),
                    payload={
                        "activity": {
                            "id": f"activity:{row.id}",
                            "kind": "recovery",
                            "title": "恢复未完成的只读操作",
                            "summary": "上次执行在结算前中断，正在使用同一调用标识安全重试。",
                            "status": "running",
                            "tool_invocation_id": str(row.id),
                        }
                    },
                )
                retryable.append(self._domain(row))
                continue
            self.settle(
                lease=lease,
                invocation_id=str(row.id),
                status=ObservationStatus.UNKNOWN,
                model_visible_summary=(
                    "The previous tool execution was interrupted and its outcome cannot be proven. "
                    "Do not assume it succeeded; choose a safe alternative or explain the uncertainty."
                ),
                error_code="TOOL_OUTCOME_UNKNOWN",
                error_message="Tool execution was interrupted before durable settlement.",
                retryable=False,
            )
        self.session.flush()
        return retryable

    def settle(
        self,
        *,
        lease: SessionLease,
        invocation_id: str,
        status: ObservationStatus,
        model_visible_summary: str,
        structured_result_ref: str | None = None,
        artifact_ids: list[str] | None = None,
        facts: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool = False,
    ) -> Observation:
        begin_agent_write(self.session)
        row = self.session.execute(
            select(AgentToolInvocation).where(AgentToolInvocation.id == invocation_id).with_for_update()
        ).scalar_one()
        if row.session_id != lease.session_id:
            raise ValueError("ToolInvocation is outside the Session")
        if row.status not in {
            ToolInvocationStatus.RUNNING.value,
            ToolInvocationStatus.REJECTED.value,
            ToolInvocationStatus.WAITING_APPROVAL.value,
        }:
            raise ValueError(f"ToolInvocation cannot settle from status {row.status}")
        existing = self.session.execute(
            select(AgentObservationRecord).where(
                AgentObservationRecord.tool_invocation_id == invocation_id
            )
        ).scalar_one_or_none()
        if existing is not None:
            return self._observation(existing, row)

        sequence = int(
            self.session.execute(
                select(func.coalesce(func.max(AgentObservationRecord.sequence), 0)).where(
                    AgentObservationRecord.run_id == row.run_id
                )
            ).scalar_one()
        ) + 1
        now = _utcnow()
        observation = AgentObservationRecord(
            id=f"observation_{uuid4().hex}",
            session_id=str(row.session_id),
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            tool_invocation_id=str(row.id),
            sequence=sequence,
            status=status.value,
            model_visible_summary=model_visible_summary,
            structured_result_ref=structured_result_ref,
            artifact_ids_json=_json(artifact_ids or []),
            facts_json=_json(facts or {}),
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            created_at=now,
        )
        self.session.add(observation)
        row.status = {
            ObservationStatus.SUCCEEDED: ToolInvocationStatus.SUCCEEDED.value,
            ObservationStatus.FAILED: ToolInvocationStatus.FAILED.value,
            ObservationStatus.REJECTED: ToolInvocationStatus.REJECTED.value,
            ObservationStatus.UNKNOWN: ToolInvocationStatus.UNKNOWN.value,
        }[status]
        row.result_ref = structured_result_ref
        row.error_code = error_code
        row.error_message = error_message
        row.completed_at = now
        self.session.flush()
        domain = self._observation(observation, row)
        self.sessions.append_event(
            lease=lease,
            event_type=(
                RuntimeEventType.TOOL_COMPLETED
                if status is ObservationStatus.SUCCEEDED
                else RuntimeEventType.TOOL_FAILED
            ),
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            payload={"tool_invocation_id": row.id, "status": row.status},
        )
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.OBSERVATION_CREATED,
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            payload={"observation": domain.model_dump(mode="json")},
        )
        return domain

    @staticmethod
    def _domain(row: AgentToolInvocation) -> ToolInvocation:
        return ToolInvocation(
            id=str(row.id),
            session_id=str(row.session_id),
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            provider_call_id=str(row.provider_call_id),
            tool_name=str(row.tool_name),
            tool_version=str(row.tool_version),
            authorized_input=json.loads(str(row.input_json)),
            authorized_input_hash=str(row.input_hash),
            idempotency_key=str(row.idempotency_key),
            status=ToolInvocationStatus(str(row.status)),
            policy=json.loads(str(row.policy_json or "{}")),
            recovery_policy=str(row.recovery_policy),
            attempt_count=int(row.attempt_count or 0),
        )

    @staticmethod
    def _observation(row: AgentObservationRecord, invocation: AgentToolInvocation) -> Observation:
        return Observation(
            id=str(row.id),
            session_id=str(row.session_id),
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            tool_invocation_id=str(row.tool_invocation_id),
            tool_name=str(invocation.tool_name),
            tool_version=str(invocation.tool_version),
            status=ObservationStatus(str(row.status)),
            model_visible_summary=str(row.model_visible_summary),
            structured_result_ref=str(row.structured_result_ref) if row.structured_result_ref else None,
            artifact_ids=json.loads(str(row.artifact_ids_json or "[]")),
            facts=json.loads(str(row.facts_json or "{}")),
            error_code=str(row.error_code) if row.error_code else None,
            error_message=str(row.error_message) if row.error_message else None,
            retryable=bool(row.retryable),
            sequence=int(row.sequence),
        )
