"""Durable ToolInvocation intent and settlement repository."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.agent.events import RuntimeEventType
from engine.agent.observation import (
    Observation,
    ObservationStatus,
    serialize_model_observation,
)
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.run_item import (
    dump_run_item,
    function_call_output_item,
    function_call_item,
)
from engine.agent.session import SessionLease
from engine.agent.tool import ToolInvocation, ToolInvocationStatus
from engine.json_codec import canonical_dumps as _json, loads
from engine.models import AgentObservationRecord, AgentToolInvocation, AgentTurn
from engine.tools.materialization import ToolMaterialization
from engine.tools.runtime.base import ToolRecoveryPolicy


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
            presentation_json=_json(tool.presentation),
            recovery_policy=tool.recovery_policy.value,
            attempt_count=0,
            created_at=_utcnow(),
        )
        self.session.add(row)
        self.session.flush()
        self.sessions.append_event(
            lease=lease,
            event_type=(
                RuntimeEventType.RUN_ITEM_FAILED
                if status is ToolInvocationStatus.REJECTED
                else RuntimeEventType.RUN_ITEM_STARTED
            ),
            run_id=run_id,
            turn_id=turn_id,
            payload={"item": dump_run_item(function_call_item(row))},
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
            event_type=RuntimeEventType.RUN_ITEM_UPDATED,
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            payload={"item": dump_run_item(function_call_item(row))},
        )
        self.session.flush()
        return self._domain(row)

    def mark_waiting_input(
        self,
        *,
        lease: SessionLease,
        invocation_id: str,
    ) -> ToolInvocation:
        """Suspend an interaction call until its user response is durable."""

        begin_agent_write(self.session)
        row = self.session.execute(
            select(AgentToolInvocation)
            .where(AgentToolInvocation.id == invocation_id)
            .with_for_update()
        ).scalar_one()
        if row.session_id != lease.session_id:
            raise ValueError("ToolInvocation is outside the Session")
        if row.status != ToolInvocationStatus.REQUESTED.value:
            raise ValueError(
                f"ToolInvocation cannot wait for input from status {row.status}"
            )
        row.status = ToolInvocationStatus.WAITING_INPUT.value
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.RUN_ITEM_UPDATED,
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            payload={"item": dump_run_item(function_call_item(row))},
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
            event_type=RuntimeEventType.RUN_ITEM_UPDATED,
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            payload={"item": dump_run_item(function_call_item(row))},
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

    def cancel_active_for_run(
        self,
        *,
        lease: SessionLease,
        run_id: str,
    ) -> list[Observation]:
        """Atomically terminalize every non-terminal invocation in a cancelled Run."""
        begin_agent_write(self.session)
        rows = self.session.execute(
            select(AgentToolInvocation).where(
                AgentToolInvocation.run_id == run_id,
                AgentToolInvocation.status.in_(
                    [
                        ToolInvocationStatus.REQUESTED.value,
                        ToolInvocationStatus.WAITING_APPROVAL.value,
                        ToolInvocationStatus.WAITING_INPUT.value,
                        ToolInvocationStatus.RUNNING.value,
                    ]
                ),
            ).order_by(AgentToolInvocation.created_at).with_for_update()
        ).scalars().all()
        observations: list[Observation] = []
        for row in rows:
            if str(row.session_id) != lease.session_id:
                raise ValueError("ToolInvocation is outside the Session")
            observations.append(
                self.settle(
                    lease=lease,
                    invocation_id=str(row.id),
                    status=ObservationStatus.CANCELLED,
                    model_visible_summary="The tool execution was cancelled with its Run.",
                    error_code="TOOL_CANCELLED",
                    error_message="Tool execution was cancelled.",
                    contributes_progress=False,
                    retryable=False,
                )
            )
        self.session.flush()
        return observations

    def recover_interrupted(self, *, lease: SessionLease, run_id: str) -> list[ToolInvocation]:
        """Settle or requeue invocations left running by a crashed worker."""
        begin_agent_write(self.session)
        rows = self.session.execute(
            select(AgentToolInvocation).where(
                AgentToolInvocation.run_id == run_id,
                AgentToolInvocation.status == ToolInvocationStatus.RUNNING.value,
            ).order_by(AgentToolInvocation.created_at).with_for_update()
        ).scalars().all()
        recoverable: list[ToolInvocation] = []
        for row in rows:
            if str(row.session_id) != lease.session_id:
                raise ValueError("ToolInvocation is outside the Session")
            policy = ToolRecoveryPolicy(str(row.recovery_policy))
            if policy in {
                ToolRecoveryPolicy.RETRY_SAFE,
                ToolRecoveryPolicy.RECONCILE,
            }:
                row.status = ToolInvocationStatus.REQUESTED.value
                row.started_at = None
                self.sessions.append_event(
                    lease=lease,
                    event_type=RuntimeEventType.RUN_ITEM_UPDATED,
                    run_id=run_id,
                    turn_id=str(row.turn_id),
                    payload={"item": dump_run_item(function_call_item(row))},
                )
                recoverable.append(self._domain(row))
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
        return recoverable

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
        capabilities: tuple[str, ...] | list[str] | None = None,
        contributes_progress: bool = True,
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
            ToolInvocationStatus.REQUESTED.value,
            ToolInvocationStatus.RUNNING.value,
            ToolInvocationStatus.REJECTED.value,
            ToolInvocationStatus.WAITING_APPROVAL.value,
            ToolInvocationStatus.WAITING_INPUT.value,
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
        resolved_artifact_ids = artifact_ids or []
        resolved_facts = facts or {}
        model_output = serialize_model_observation(
            status=status.value,
            summary=model_visible_summary,
            facts=resolved_facts,
            artifact_ids=resolved_artifact_ids,
            retryable=retryable,
            error_code=error_code,
            error_message=error_message,
        )
        observation = AgentObservationRecord(
            id=f"observation_{uuid4().hex}",
            session_id=str(row.session_id),
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            tool_invocation_id=str(row.id),
            sequence=sequence,
            status=status.value,
            model_visible_summary=model_visible_summary,
            model_output_json=model_output,
            structured_result_ref=structured_result_ref,
            artifact_ids_json=_json(resolved_artifact_ids),
            facts_json=_json(resolved_facts),
            semantic_capabilities_json=_json(list(capabilities or [])),
            contributes_progress=contributes_progress,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            created_at=now,
        )
        self.session.add(observation)
        row.status = {
            ObservationStatus.SUCCEEDED: ToolInvocationStatus.SUCCEEDED.value,
            ObservationStatus.FAILED: ToolInvocationStatus.FAILED.value,
            ObservationStatus.CANCELLED: ToolInvocationStatus.CANCELLED.value,
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
                RuntimeEventType.RUN_ITEM_COMPLETED
                if status is ObservationStatus.SUCCEEDED
                else RuntimeEventType.RUN_ITEM_CANCELLED
                if status is ObservationStatus.CANCELLED
                else RuntimeEventType.RUN_ITEM_FAILED
            ),
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            payload={"item": dump_run_item(function_call_item(row))},
        )
        self.sessions.append_event(
            lease=lease,
            event_type=(
                RuntimeEventType.RUN_ITEM_COMPLETED
                if status is ObservationStatus.SUCCEEDED
                else RuntimeEventType.RUN_ITEM_CANCELLED
                if status is ObservationStatus.CANCELLED
                else RuntimeEventType.RUN_ITEM_FAILED
            ),
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            payload={
                "item": dump_run_item(
                    function_call_output_item(row, observation)
                )
            },
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
            authorized_input=loads(str(row.input_json)),
            authorized_input_hash=str(row.input_hash),
            idempotency_key=str(row.idempotency_key),
            status=ToolInvocationStatus(str(row.status)),
            policy=loads(str(row.policy_json or "{}")),
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
            model_output=str(row.model_output_json),
            structured_result_ref=str(row.structured_result_ref) if row.structured_result_ref else None,
            artifact_ids=loads(str(row.artifact_ids_json or "[]")),
            facts=loads(str(row.facts_json or "{}")),
            capabilities=tuple(loads(str(row.semantic_capabilities_json or "[]"))),
            contributes_progress=bool(row.contributes_progress),
            error_code=str(row.error_code) if row.error_code else None,
            error_message=str(row.error_message) if row.error_message else None,
            retryable=bool(row.retryable),
            sequence=int(row.sequence),
        )
