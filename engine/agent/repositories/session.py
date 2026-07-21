"""Session admission, ownership, Turn and RuntimeEventLog transactions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy import event
from sqlalchemy.orm import Session

from engine.agent.events import (
    COMMIT_NOTIFICATIONS,
    RuntimeEvent,
    RuntimeEventType,
    validate_runtime_event_payload,
)
from engine.agent.run import RunStatus, SessionLeaseConflict, TERMINAL_RUN_STATUSES
from engine.agent.session import DeliveryMode, SessionInputStatus, SessionLease
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.models import (
    AgentEventRecord,
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentSessionInput,
    AgentTurn,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


EVENT_REPLAY_RETAINED = 2_000
EVENT_COMPACTION_TRIGGER = 2_500


class EventHistoryGap(RuntimeError):
    """The requested cursor predates the canonical snapshot replay boundary."""

    def __init__(self, *, floor_sequence: int, current_sequence: int) -> None:
        super().__init__("The event cursor is older than the retained replay history.")
        self.floor_sequence = floor_sequence
        self.current_sequence = current_sequence


@dataclass(frozen=True)
class Admission:
    input_id: str
    run_id: str
    user_message_id: str
    assistant_message_id: str
    input_sequence: int
    run_version: int


class SessionRepository:
    """Repository methods participate in the caller's short database transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def admit(
        self,
        *,
        session_id: str,
        datasource_id: str,
        datasource_generation: int,
        content: str,
        idempotency_key: str,
        llm_credential_id: str,
        api_base: str | None,
        model_name: str | None,
        request_payload: dict[str, Any],
        delivery_mode: DeliveryMode = DeliveryMode.QUEUE,
        selected_artifact_ids: list[str] | None = None,
        workspace_context: dict[str, Any] | None = None,
        reply_to_request_id: str | None = None,
    ) -> Admission:
        begin_agent_write(self.session)
        existing = self.session.execute(
            select(AgentSessionInput).where(
                AgentSessionInput.session_id == session_id,
                AgentSessionInput.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return self._admission_from_input(existing)

        aggregate = self._session_for_update(session_id)
        if str(aggregate.datasource_id) != datasource_id:
            raise ValueError("Session datasource does not match admitted input")

        if delivery_mode is DeliveryMode.STEER:
            active_run = self.session.execute(
                select(AgentRun)
                .where(
                    AgentRun.session_id == session_id,
                    AgentRun.status == RunStatus.RUNNING.value,
                )
                .order_by(AgentRun.session_sequence.desc())
                .with_for_update()
            ).scalars().first()
            if active_run is not None:
                return self._admit_steer(
                    aggregate=aggregate,
                    run=active_run,
                    content=content,
                    idempotency_key=idempotency_key,
                    selected_artifact_ids=selected_artifact_ids,
                    workspace_context=workspace_context,
                )

        if delivery_mode is DeliveryMode.CANCEL_AND_REPLACE:
            self._cancel_superseded_work(aggregate)

        aggregate.input_sequence = int(aggregate.input_sequence or 0) + 1
        aggregate.message_sequence = int(aggregate.message_sequence or 0) + 2
        now = _utcnow()
        input_id = f"input_{uuid4().hex}"
        run_id = f"run_{uuid4().hex}"
        user_message_id = f"message_user_{uuid4().hex}"
        assistant_message_id = f"message_assistant_{uuid4().hex}"
        user_sequence = int(aggregate.message_sequence) - 1
        assistant_sequence = int(aggregate.message_sequence)

        admitted = AgentSessionInput(
            id=input_id,
            session_id=session_id,
            run_id=run_id,
            message_id=user_message_id,
            sequence=int(aggregate.input_sequence),
            idempotency_key=idempotency_key,
            content=content,
            delivery_mode=delivery_mode.value,
            selected_artifact_ids_json=_json(selected_artifact_ids or []),
            workspace_context_json=_json(workspace_context or {}),
            reply_to_request_id=reply_to_request_id,
            status=SessionInputStatus.ADMITTED.value,
            admitted_at=now,
        )
        self.session.add_all(
            [
                AgentMessage(
                    id=user_message_id,
                    session_id=session_id,
                    role="user",
                    content=content,
                    status="completed",
                    sequence=user_sequence,
                    created_at=now,
                    updated_at=now,
                ),
                AgentMessage(
                    id=assistant_message_id,
                    session_id=session_id,
                    role="assistant",
                    content="",
                    status="created",
                    sequence=assistant_sequence,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        self.session.flush()
        self.session.add(admitted)
        self.session.flush()
        self.session.add(
            AgentRun(
                id=run_id,
                session_id=session_id,
                input_id=input_id,
                session_sequence=int(aggregate.input_sequence),
                datasource_id=datasource_id,
                datasource_generation=datasource_generation,
                llm_credential_id=llm_credential_id,
                api_base=api_base,
                model_name=model_name,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                question=content,
                status=RunStatus.QUEUED.value,
                version=0,
                lease_token=0,
                execution_id=f"agent_{run_id}",
                request_json=_json(request_payload),
                cancel_requested=False,
                created_at=now,
                updated_at=now,
            )
        )
        # Event rows have database foreign keys but deliberately no ORM
        # relationship to the aggregate. Flush the admitted entities first so
        # SQLAlchemy cannot schedule the event insert ahead of its Run.
        self.session.flush()
        self._append_event(
            aggregate,
            RuntimeEventType.SESSION_INPUT_ADMITTED,
            run_id=run_id,
            payload={
                "session_input": {
                    "id": input_id,
                    "sequence": int(aggregate.input_sequence),
                    "delivery_mode": delivery_mode.value,
                    "selected_artifact_ids": selected_artifact_ids or [],
                    "reply_to_request_id": reply_to_request_id,
                },
                "user_message_id": user_message_id,
            },
            now=now,
        )
        self._append_event(
            aggregate,
            RuntimeEventType.RUN_CREATED,
            run_id=run_id,
            payload={
                "run": {
                    "id": run_id,
                    "status": RunStatus.QUEUED.value,
                    "version": 0,
                    "input_id": input_id,
                    "assistant_message_id": assistant_message_id,
                }
            },
            now=now,
        )
        self.session.flush()
        return Admission(
            input_id=input_id,
            run_id=run_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            input_sequence=int(aggregate.input_sequence),
            run_version=0,
        )

    def consume_steering_inputs(self, *, lease: SessionLease, run_id: str) -> list[str]:
        """Consume formal steer inputs at a Turn boundary under the Session lease."""
        aggregate = self._session_for_update(lease.session_id)
        self._require_lease(aggregate, lease)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_run_lease(run, lease)
        rows = self.session.execute(
            select(AgentSessionInput)
            .where(
                AgentSessionInput.run_id == run_id,
                AgentSessionInput.delivery_mode == DeliveryMode.STEER.value,
                AgentSessionInput.status == SessionInputStatus.ADMITTED.value,
            )
            .order_by(AgentSessionInput.sequence)
            .with_for_update()
        ).scalars().all()
        if not rows:
            return []
        now = _utcnow()
        for row in rows:
            row.status = SessionInputStatus.CONSUMED.value
            row.consumed_at = now
        run.version = int(run.version or 0) + 1
        run.updated_at = now
        self._append_event(
            aggregate,
            RuntimeEventType.SESSION_CONTEXT_UPDATED,
            run_id=run_id,
            payload={
                "reason": "steer_inputs_consumed",
                "input_ids": [str(row.id) for row in rows],
            },
            now=now,
        )
        self.session.flush()
        return [str(row.content) for row in rows]

    def claim(
        self,
        *,
        session_id: str,
        owner: str,
        ttl_seconds: int = 30,
        now: datetime | None = None,
    ) -> SessionLease | None:
        current_time = now or _utcnow()
        aggregate = self._session_for_update(session_id)
        expires_at = _aware(aggregate.lease_expires_at)
        active_other_owner = (
            aggregate.lease_owner is not None
            and aggregate.lease_owner != owner
            and expires_at is not None
            and expires_at > current_time
        )
        if active_other_owner:
            return None

        if aggregate.lease_owner != owner or expires_at is None or expires_at <= current_time:
            aggregate.lease_token = int(aggregate.lease_token or 0) + 1
        aggregate.lease_owner = owner
        aggregate.lease_expires_at = current_time + timedelta(seconds=ttl_seconds)
        self.session.flush()
        return SessionLease(
            session_id=session_id,
            owner=owner,
            token=int(aggregate.lease_token),
            expires_at=_aware(aggregate.lease_expires_at) or current_time,
        )

    def heartbeat(
        self,
        *,
        lease: SessionLease,
        ttl_seconds: int = 30,
        now: datetime | None = None,
    ) -> SessionLease:
        current_time = now or _utcnow()
        aggregate = self._session_for_update(lease.session_id)
        self._require_lease(aggregate, lease)
        aggregate.lease_expires_at = current_time + timedelta(seconds=ttl_seconds)
        self.session.flush()
        return lease.model_copy(update={"expires_at": _aware(aggregate.lease_expires_at)})

    def release(self, *, lease: SessionLease) -> None:
        aggregate = self._session_for_update(lease.session_id)
        self._require_lease(aggregate, lease)
        aggregate.lease_owner = None
        aggregate.lease_expires_at = None
        self.session.flush()

    def bind_run(self, *, lease: SessionLease, run_id: str) -> None:
        aggregate = self._session_for_update(lease.session_id)
        self._require_lease(aggregate, lease)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        if str(run.session_id) != lease.session_id:
            raise SessionLeaseConflict("Run is outside the claimed Session")
        if run.status not in {
            RunStatus.RUNNING.value,
            RunStatus.CANCELLING.value,
        }:
            raise RuntimeError(f"Cannot bind worker to Run status {run.status}")
        run.lease_token = lease.token
        run.updated_at = _utcnow()
        self.session.flush()

    def promote_next_input(self, *, lease: SessionLease) -> str | None:
        aggregate = self._session_for_update(lease.session_id)
        self._require_lease(aggregate, lease)
        admitted = self.session.execute(
            select(AgentSessionInput)
            .where(
                AgentSessionInput.session_id == lease.session_id,
                AgentSessionInput.status == SessionInputStatus.ADMITTED.value,
            )
            .order_by(AgentSessionInput.sequence)
            .with_for_update()
        ).scalars().first()
        if admitted is None:
            return None
        run = self.session.get(AgentRun, admitted.run_id)
        if run is None:
            raise RuntimeError("Admitted SessionInput has no Run")
        now = _utcnow()
        admitted.status = SessionInputStatus.PROMOTED.value
        run.status = RunStatus.RUNNING.value
        run.version = int(run.version or 0) + 1
        run.lease_token = lease.token
        run.started_at = now
        run.updated_at = now
        self._append_event(
            aggregate,
            RuntimeEventType.SESSION_INPUT_PROMOTED,
            run_id=str(run.id),
            payload={"session_input_id": admitted.id},
            now=now,
        )
        self._append_event(
            aggregate,
            RuntimeEventType.RUN_STARTED,
            run_id=str(run.id),
            payload={"run": {"id": run.id, "status": run.status, "version": run.version}},
            now=now,
        )
        self.session.flush()
        return str(run.id)

    def start_turn(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        agent_definition_version: str,
        prompt_version: str,
        prompt_hash: str,
        context_snapshot: dict[str, Any],
        context_hash: str,
        tool_materialization: dict[str, Any],
        tool_materialization_hash: str,
        provider: str,
        model_name: str,
    ) -> AgentTurn:
        aggregate = self._session_for_update(lease.session_id)
        self._require_lease(aggregate, lease)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_run_lease(run, lease)
        if run.status != RunStatus.RUNNING.value:
            raise RuntimeError(f"Cannot start a Turn for Run status {run.status}")
        sequence = int(
            self.session.execute(
                select(func.coalesce(func.max(AgentTurn.sequence), 0)).where(AgentTurn.run_id == run_id)
            ).scalar_one()
        ) + 1
        now = _utcnow()
        turn = AgentTurn(
            id=f"turn_{uuid4().hex}",
            session_id=lease.session_id,
            run_id=run_id,
            sequence=sequence,
            status="running",
            agent_definition_version=agent_definition_version,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            context_snapshot_json=_json(context_snapshot),
            context_hash=context_hash,
            tool_materialization_json=_json(tool_materialization),
            tool_materialization_hash=tool_materialization_hash,
            provider=provider,
            model_name=model_name,
            created_at=now,
        )
        self.session.add(turn)
        run.current_turn_id = turn.id
        run.version = int(run.version) + 1
        run.updated_at = now
        self.session.flush()
        self._append_event(
            aggregate,
            RuntimeEventType.TURN_STARTED,
            run_id=run_id,
            turn_id=turn.id,
            payload={"turn": {"id": turn.id, "sequence": sequence, "status": "running"}},
            now=now,
        )
        self.session.flush()
        return turn

    def list_events(self, session_id: str, *, after_sequence: int = 0, limit: int = 500) -> list[RuntimeEvent]:
        aggregate = self.session.get(AgentSession, session_id)
        if aggregate is None:
            raise KeyError(f"Unknown Agent Session: {session_id}")
        floor_sequence = int(aggregate.event_floor_sequence or 0)
        if after_sequence < floor_sequence:
            raise EventHistoryGap(
                floor_sequence=floor_sequence,
                current_sequence=int(aggregate.event_sequence or 0),
            )
        records = self.session.execute(
            select(AgentEventRecord)
            .where(
                AgentEventRecord.session_id == session_id,
                AgentEventRecord.sequence > after_sequence,
            )
            .order_by(AgentEventRecord.sequence)
            .limit(limit)
        ).scalars()
        return [
            RuntimeEvent(
                event_id=str(record.id),
                event_type=RuntimeEventType(str(record.type)),
                event_version=int(record.event_version),
                session_id=str(record.session_id),
                run_id=str(record.run_id) if record.run_id else None,
                turn_id=str(record.turn_id) if record.turn_id else None,
                sequence=int(record.sequence),
                timestamp=_aware(record.created_at) or _utcnow(),
                payload=json.loads(str(record.payload_json or "{}")),
            )
            for record in records
        ]

    def append_event(
        self,
        *,
        lease: SessionLease,
        event_type: RuntimeEventType,
        run_id: str | None,
        payload: dict[str, Any],
        turn_id: str | None = None,
    ) -> int:
        aggregate = self._session_for_update(lease.session_id)
        self._require_lease(aggregate, lease)
        if run_id is not None:
            run = self.session.get(AgentRun, run_id)
            if run is None:
                raise ValueError(f"Agent Run does not exist: {run_id}")
            self._require_run_lease(run, lease)
        self._append_event(
            aggregate,
            event_type,
            run_id=run_id,
            turn_id=turn_id,
            payload=payload,
            now=_utcnow(),
        )
        self.session.flush()
        return int(aggregate.event_sequence)

    def append_user_command_event(
        self,
        *,
        session_id: str,
        run_id: str,
        event_type: RuntimeEventType,
        payload: dict[str, Any],
        turn_id: str | None = None,
    ) -> int:
        """Append an event produced by a user command while a worker owns the lease.

        Commands such as cancellation must remain admissible while the Run is
        executing. The Session row lock still serializes the aggregate sequence;
        the worker lease deliberately does not fence the user's command.
        """
        aggregate = self._session_for_update(session_id)
        run = self.session.get(AgentRun, run_id)
        if run is None or str(run.session_id) != session_id:
            raise ValueError("Run is outside the Session")
        self._append_event(
            aggregate,
            event_type,
            run_id=run_id,
            turn_id=turn_id,
            payload=payload,
            now=_utcnow(),
        )
        self.session.flush()
        return int(aggregate.event_sequence)

    def add_response_input(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        content: str,
        idempotency_key: str,
        reply_to_request_id: str,
        now: datetime | None = None,
    ) -> AgentMessage:
        """Persist a user's response to an in-flight agent request."""
        aggregate = self._session_for_update(lease.session_id)
        self._require_lease(aggregate, lease)
        run = self.session.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Agent Run does not exist: {run_id}")
        self._require_run_lease(run, lease)

        current_time = now or _utcnow()
        aggregate.input_sequence = int(aggregate.input_sequence or 0) + 1
        aggregate.message_sequence = int(aggregate.message_sequence or 0) + 1
        message = AgentMessage(
            id=f"message_user_{uuid4().hex}",
            session_id=lease.session_id,
            role="user",
            content=content,
            status="completed",
            sequence=int(aggregate.message_sequence),
            created_at=current_time,
            updated_at=current_time,
        )
        self.session.add(message)
        self.session.flush()
        self.session.add(
            AgentSessionInput(
                id=f"input_{uuid4().hex}",
                session_id=lease.session_id,
                run_id=run_id,
                message_id=message.id,
                sequence=int(aggregate.input_sequence),
                idempotency_key=idempotency_key,
                content=content,
                delivery_mode=DeliveryMode.RESPOND.value,
                selected_artifact_ids_json="[]",
                workspace_context_json="{}",
                reply_to_request_id=reply_to_request_id,
                status=SessionInputStatus.CONSUMED.value,
                admitted_at=current_time,
                consumed_at=current_time,
            )
        )
        self.session.flush()
        return message

    def select_artifact(self, *, session_id: str, artifact_id: str, selected_by: str) -> None:
        from engine.models import AgentArtifactRecord

        aggregate = self._session_for_update(session_id)
        artifact = self.session.get(AgentArtifactRecord, artifact_id)
        if artifact is None or str(artifact.session_id) != session_id:
            raise ValueError("Artifact is outside the Session")
        aggregate.selected_artifact_id = artifact_id
        self._append_event(
            aggregate,
            RuntimeEventType.ARTIFACT_SELECTED,
            run_id=str(artifact.run_id),
            turn_id=str(artifact.turn_id) if artifact.turn_id else None,
            payload={"selection": {
                "session_id": session_id, "artifact_id": artifact_id,
                "selected_by": selected_by,
            }},
            now=_utcnow(),
        )
        self.session.flush()

    def _append_event(
        self,
        aggregate: AgentSession,
        event_type: RuntimeEventType,
        *,
        run_id: str | None,
        payload: dict[str, Any],
        now: datetime,
        turn_id: str | None = None,
    ) -> None:
        event_version = validate_runtime_event_payload(event_type, payload)
        aggregate.event_sequence = int(aggregate.event_sequence or 0) + 1
        self.session.add(
            AgentEventRecord(
                id=f"event_{uuid4().hex}",
                session_id=str(aggregate.id),
                run_id=run_id,
                turn_id=turn_id,
                sequence=int(aggregate.event_sequence),
                type=event_type.value,
                event_version=event_version,
                payload_json=_json(payload),
                created_at=now,
            )
        )
        self._compact_event_log(aggregate)
        pending = self.session.info.setdefault("dbfox_agent_event_sessions", set())
        pending.add(str(aggregate.id))

    def _compact_event_log(self, aggregate: AgentSession) -> None:
        """Bound replay storage; canonical tables remain the durable snapshot truth."""
        current = int(aggregate.event_sequence or 0)
        floor = int(aggregate.event_floor_sequence or 0)
        if current - floor <= EVENT_COMPACTION_TRIGGER:
            return
        next_floor = current - EVENT_REPLAY_RETAINED
        self.session.execute(
            delete(AgentEventRecord).where(
                AgentEventRecord.session_id == str(aggregate.id),
                AgentEventRecord.sequence <= next_floor,
            )
        )
        aggregate.event_floor_sequence = next_floor

    def _admit_steer(
        self,
        *,
        aggregate: AgentSession,
        run: AgentRun,
        content: str,
        idempotency_key: str,
        selected_artifact_ids: list[str] | None,
        workspace_context: dict[str, Any] | None,
    ) -> Admission:
        aggregate.input_sequence = int(aggregate.input_sequence or 0) + 1
        aggregate.message_sequence = int(aggregate.message_sequence or 0) + 1
        now = _utcnow()
        input_id = f"input_{uuid4().hex}"
        message_id = f"message_user_{uuid4().hex}"
        message = AgentMessage(
            id=message_id,
            session_id=str(aggregate.id),
            role="user",
            content=content,
            status="completed",
            sequence=int(aggregate.message_sequence),
            created_at=now,
            updated_at=now,
        )
        self.session.add(message)
        self.session.flush()
        admitted = AgentSessionInput(
            id=input_id,
            session_id=str(aggregate.id),
            run_id=str(run.id),
            message_id=message_id,
            sequence=int(aggregate.input_sequence),
            idempotency_key=idempotency_key,
            content=content,
            delivery_mode=DeliveryMode.STEER.value,
            selected_artifact_ids_json=_json(selected_artifact_ids or []),
            workspace_context_json=_json(workspace_context or {}),
            status=SessionInputStatus.ADMITTED.value,
            admitted_at=now,
        )
        self.session.add(admitted)
        self.session.flush()
        self._append_event(
            aggregate,
            RuntimeEventType.SESSION_INPUT_ADMITTED,
            run_id=str(run.id),
            payload={
                "session_input": {
                    "id": input_id,
                    "sequence": int(aggregate.input_sequence),
                    "delivery_mode": DeliveryMode.STEER.value,
                    "selected_artifact_ids": selected_artifact_ids or [],
                },
                "user_message_id": message_id,
            },
            now=now,
        )
        self.session.flush()
        return Admission(
            input_id=input_id,
            run_id=str(run.id),
            user_message_id=message_id,
            assistant_message_id=str(run.assistant_message_id),
            input_sequence=int(aggregate.input_sequence),
            run_version=int(run.version or 0),
        )

    def _cancel_superseded_work(self, aggregate: AgentSession) -> None:
        rows = self.session.execute(
            select(AgentRun)
            .where(
                AgentRun.session_id == aggregate.id,
                AgentRun.status.not_in([status.value for status in TERMINAL_RUN_STATUSES]),
            )
            .order_by(AgentRun.session_sequence)
            .with_for_update()
        ).scalars().all()
        now = _utcnow()
        for run in rows:
            run.cancel_requested = True
            if run.status == RunStatus.RUNNING.value:
                run.status = RunStatus.CANCELLING.value
                event_type = RuntimeEventType.RUN_CANCELLING
            else:
                run.status = RunStatus.CANCELLED.value
                run.completed_at = now
                event_type = RuntimeEventType.RUN_CANCELLED
                assistant = self.session.get(AgentMessage, run.assistant_message_id)
                if assistant is not None:
                    assistant.status = "cancelled"
                    assistant.updated_at = now
            run.version = int(run.version or 0) + 1
            run.updated_at = now
            inputs = self.session.execute(
                select(AgentSessionInput).where(
                    AgentSessionInput.run_id == run.id,
                    AgentSessionInput.status == SessionInputStatus.ADMITTED.value,
                ).with_for_update()
            ).scalars().all()
            for admitted in inputs:
                admitted.status = SessionInputStatus.CANCELLED.value
                admitted.consumed_at = now
            self._append_event(
                aggregate,
                event_type,
                run_id=str(run.id),
                payload={"run": {
                    "id": str(run.id), "status": str(run.status), "version": int(run.version),
                    "reason": "superseded_by_user_input",
                }},
                now=now,
            )

    def _session_for_update(self, session_id: str) -> AgentSession:
        begin_agent_write(self.session)
        aggregate = self.session.execute(
            select(AgentSession).where(AgentSession.id == session_id).with_for_update()
        ).scalar_one_or_none()
        if aggregate is None:
            raise ValueError(f"Agent Session does not exist: {session_id}")
        return aggregate

    @staticmethod
    def _require_lease(aggregate: AgentSession, lease: SessionLease) -> None:
        if aggregate.lease_owner != lease.owner or int(aggregate.lease_token or 0) != lease.token:
            raise SessionLeaseConflict("Session lease has been replaced")
        expires_at = _aware(aggregate.lease_expires_at)
        if expires_at is None or expires_at <= _utcnow():
            raise SessionLeaseConflict("Session lease has expired")

    @staticmethod
    def _require_run_lease(run: AgentRun, lease: SessionLease) -> None:
        if str(run.session_id) != lease.session_id or int(run.lease_token or 0) != lease.token:
            raise SessionLeaseConflict("Run is fenced by a different Session lease")

    def _admission_from_input(self, admitted: AgentSessionInput) -> Admission:
        run = self.session.get(AgentRun, admitted.run_id)
        if run is None or not admitted.message_id or not run.assistant_message_id:
            raise RuntimeError("Idempotent SessionInput has an incomplete Run projection")
        return Admission(
            input_id=str(admitted.id),
            run_id=str(run.id),
            user_message_id=str(admitted.message_id),
            assistant_message_id=str(run.assistant_message_id),
            input_sequence=int(admitted.sequence),
            run_version=int(run.version),
        )


@event.listens_for(Session, "after_commit")
def _notify_agent_event_commits(session: Session) -> None:
    for session_id in session.info.pop("dbfox_agent_event_sessions", set()):
        COMMIT_NOTIFICATIONS.publish(str(session_id))


@event.listens_for(Session, "after_rollback")
def _discard_agent_event_notifications(session: Session) -> None:
    session.info.pop("dbfox_agent_event_sessions", None)
