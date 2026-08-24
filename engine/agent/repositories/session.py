"""Session admission, ownership, Turn and RuntimeEventLog transactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy import event
from sqlalchemy.orm import Session

from engine.agent.events import (
    COMMIT_NOTIFICATIONS,
    RuntimeEventType,
)
from engine.agent.repositories.events import EventRepository
from engine.agent.run import RunPhase, RunStatus, SessionLeaseConflict, TERMINAL_RUN_STATUSES
from engine.agent.run_item import (
    dump_run_item,
    project_run,
    user_message_item,
)
from engine.agent.session import DeliveryMode, SessionInputStatus, SessionLease
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.resource_refs import dump_resource_refs
from engine.json_codec import canonical_dumps as _json
from engine.models import (
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentSessionInput,
    AgentTurn,
)
from engine.tools.runtime.attempt import ResourceScopeRef


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Admission:
    input_id: str
    run_id: str
    user_message_id: str
    assistant_message_id: str
    input_sequence: int
    run_version: int


@dataclass(frozen=True)
class SessionDeletion:
    status: Literal["ok", "deleting"]
    running_invocations: tuple[tuple[str, str], ...] = ()


class SessionRepository:
    """Repository methods participate in the caller's short database transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.events = EventRepository(session)

    def create(
        self,
        *,
        project_id: str,
        title: str,
    ) -> AgentSession:
        begin_agent_write(self.session)
        now = _utcnow()
        aggregate = AgentSession(
            project_id=project_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        self.session.add(aggregate)
        self.session.flush()
        return aggregate

    def update_metadata(
        self,
        *,
        session_id: str,
        title: str | None,
        archived: bool | None,
    ) -> AgentSession | None:
        begin_agent_write(self.session)
        aggregate = self.session.execute(
            select(AgentSession)
            .where(AgentSession.id == session_id)
            .with_for_update()
        ).scalar_one_or_none()
        if aggregate is None or aggregate.deleted_at is not None:
            return None
        if title is not None:
            aggregate.title = title
        if archived is not None:
            aggregate.archived_at = _utcnow() if archived else None
        aggregate.updated_at = _utcnow()
        self.session.flush()
        return aggregate

    def request_delete(self, *, session_id: str) -> SessionDeletion:
        """Delete an idle Session or atomically request cancellation of its work."""

        begin_agent_write(self.session)
        aggregate = self.session.execute(
            select(AgentSession)
            .where(AgentSession.id == session_id)
            .with_for_update()
        ).scalar_one_or_none()
        if aggregate is None or aggregate.deleted_at is not None:
            return SessionDeletion(status="ok")
        active_runs = list(self.session.execute(
            select(AgentRun).where(
                AgentRun.session_id == session_id,
                AgentRun.status.not_in(
                    [status.value for status in TERMINAL_RUN_STATUSES]
                ),
            ).with_for_update()
        ).scalars())
        if not active_runs:
            self.session.delete(aggregate)
            self.session.flush()
            return SessionDeletion(status="ok")

        now = _utcnow()
        aggregate.deleted_at = now
        aggregate.archived_at = now
        aggregate.updated_at = now
        from engine.agent.repositories.run import RunRepository

        runs = RunRepository(self.session)
        running_invocations: list[tuple[str, str]] = []
        for run in active_runs:
            runs.request_cancel(run_id=str(run.id))
            from engine.agent.repositories.tool import ToolInvocationRepository

            running_invocations.extend(
                ToolInvocationRepository(self.session).running_invocations_for_run(
                    run_id=str(run.id),
                )
            )
        self.session.flush()
        return SessionDeletion(
            status="deleting",
            running_invocations=tuple(running_invocations),
        )

    def admit(
        self,
        *,
        session_id: str,
        resource_refs: tuple[ResourceScopeRef, ...],
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
        if aggregate.deleted_at is not None:
            raise ValueError("Cannot admit input to a deleted Session")
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
            resource_refs_json=dump_resource_refs(resource_refs),
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
                llm_credential_id=llm_credential_id,
                api_base=api_base,
                model_name=model_name,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                question=content,
                status=RunStatus.QUEUED.value,
                version=0,
                lease_token=0,
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
        user_message = self.session.get(AgentMessage, user_message_id)
        run = self.session.get(AgentRun, run_id)
        if user_message is None or run is None:
            raise RuntimeError("Admitted Run projection is incomplete")
        self.events.append_locked(
            aggregate,
            RuntimeEventType.RUN_STARTED,
            run_id=run_id,
            payload={"run": project_run(run)},
            now=now,
        )
        self.events.append_locked(
            aggregate,
            RuntimeEventType.RUN_ITEM_COMPLETED,
            run_id=run_id,
            payload={"item": dump_run_item(user_message_item(user_message, run_id=run_id))},
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
        self.events.append_locked(
            aggregate,
            RuntimeEventType.RUN_UPDATED,
            run_id=run_id,
            payload={"run": project_run(run)},
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

    def require_lease(self, *, lease: SessionLease) -> None:
        """Fence a repository operation that acts across the claimed Session."""
        aggregate = self._session_for_update(lease.session_id)
        self._require_lease(aggregate, lease)

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
        admitted_rows = self.session.execute(
            select(AgentSessionInput)
            .where(
                AgentSessionInput.session_id == lease.session_id,
                AgentSessionInput.status == SessionInputStatus.ADMITTED.value,
            )
            .order_by(AgentSessionInput.sequence)
            .with_for_update()
        ).scalars().all()
        for admitted in admitted_rows:
            run = self.session.get(AgentRun, admitted.run_id)
            if run is None:
                raise RuntimeError("Admitted SessionInput has no Run")
            now = _utcnow()
            if RunStatus(str(run.status)) in TERMINAL_RUN_STATUSES:
                # A steer belongs to the Run that accepted it. If that Run was
                # terminalized by a concurrent failure/cancellation, the input
                # must not revive it. Successful terminalization separately
                # checks for pending steer inputs before committing.
                admitted.status = SessionInputStatus.CANCELLED.value
                admitted.consumed_at = now
                continue
            if run.status != RunStatus.QUEUED.value:
                continue
            admitted.status = SessionInputStatus.PROMOTED.value
            run.status = RunStatus.RUNNING.value
            run.version = int(run.version or 0) + 1
            run.lease_token = lease.token
            run.started_at = now
            run.updated_at = now
            self.events.append_locked(
                aggregate,
                RuntimeEventType.RUN_UPDATED,
                run_id=str(run.id),
                payload={"run": project_run(run)},
                now=now,
            )
            self.session.flush()
            return str(run.id)
        self.session.flush()
        return None

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
        phase: RunPhase = RunPhase.WAITING_MODEL,
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
        run.current_step_name = phase.value
        run.version = int(run.version) + 1
        run.updated_at = now
        self.session.flush()
        self.events.append_locked(
            aggregate,
            RuntimeEventType.RUN_UPDATED,
            run_id=run_id,
            turn_id=turn.id,
            payload={"run": project_run(run)},
            now=now,
        )
        self.session.flush()
        return turn

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
        self.events.append_locked(
            aggregate,
            RuntimeEventType.RUN_ITEM_COMPLETED,
            run_id=run_id,
            payload={"item": dump_run_item(user_message_item(message, run_id=run_id))},
            now=current_time,
        )
        return message

    def select_artifact(self, *, session_id: str, artifact_id: str, selected_by: str) -> None:
        from engine.models import AgentArtifactRecord

        aggregate = self._session_for_update(session_id)
        artifact = self.session.get(AgentArtifactRecord, artifact_id)
        if artifact is None or str(artifact.session_id) != session_id:
            raise ValueError("Artifact is outside the Session")
        aggregate.selected_artifact_id = artifact_id
        self.session.flush()

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
        # Inherit frozen resource refs from the run's original input.
        # A steer cannot change the active Run's resource authority.
        original_input = self.session.get(AgentSessionInput, str(run.input_id))
        inherited_refs_json = (
            str(original_input.resource_refs_json)
            if original_input is not None and original_input.resource_refs_json is not None
            else None
        )

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
            resource_refs_json=inherited_refs_json,
            status=SessionInputStatus.ADMITTED.value,
            admitted_at=now,
        )
        self.session.add(admitted)
        self.session.flush()
        self.events.append_locked(
            aggregate,
            RuntimeEventType.RUN_ITEM_COMPLETED,
            run_id=str(run.id),
            payload={"item": dump_run_item(user_message_item(message, run_id=str(run.id)))},
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
        for run in rows:
            run.cancel_requested = True
            run.status = RunStatus.CANCELLING.value
            run.version = int(run.version or 0) + 1
            run.updated_at = _utcnow()
            self.events.append_locked(
                aggregate,
                RuntimeEventType.RUN_UPDATED,
                run_id=str(run.id),
                payload={"run": project_run(run)},
                now=run.updated_at,
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
