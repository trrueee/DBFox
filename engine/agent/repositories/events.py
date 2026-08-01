"""Durable RuntimeEvent log and canonical RunItem projection transactions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from engine.agent.events import RuntimeEvent, RuntimeEventType, validate_runtime_event_payload
from engine.agent.run import SessionLeaseConflict
from engine.agent.session import SessionLease
from engine.json_codec import canonical_dumps, load_object
from engine.models import AgentEventRecord, AgentRun, AgentRunItemRecord, AgentSession


EVENT_REPLAY_RETAINED = 2_000
EVENT_COMPACTION_TRIGGER = 2_500


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class EventHistoryGap(RuntimeError):
    def __init__(self, *, floor_sequence: int, current_sequence: int) -> None:
        super().__init__("The event cursor is older than the retained replay history.")
        self.floor_sequence = floor_sequence
        self.current_sequence = current_sequence


class EventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, session_id: str, *, after_sequence: int = 0, limit: int = 500) -> list[RuntimeEvent]:
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
                event_version=int(record.event_version or 1),
                session_id=str(record.session_id),
                run_id=str(record.run_id) if record.run_id else None,
                turn_id=str(record.turn_id) if record.turn_id else None,
                sequence=int(record.sequence or 0),
                timestamp=_aware(record.created_at) or _utcnow(),
                payload=load_object(str(record.payload_json or "{}")),
            )
            for record in records
        ]

    def append(
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
        self.append_locked(
            aggregate,
            event_type,
            run_id=run_id,
            turn_id=turn_id,
            payload=payload,
            now=_utcnow(),
        )
        self.session.flush()
        return int(aggregate.event_sequence or 0)

    def append_user_command(
        self,
        *,
        session_id: str,
        run_id: str,
        event_type: RuntimeEventType,
        payload: dict[str, Any],
        turn_id: str | None = None,
    ) -> int:
        aggregate = self._session_for_update(session_id)
        run = self.session.get(AgentRun, run_id)
        if run is None or str(run.session_id) != session_id:
            raise ValueError("Run is outside the Session")
        self.append_locked(
            aggregate,
            event_type,
            run_id=run_id,
            turn_id=turn_id,
            payload=payload,
            now=_utcnow(),
        )
        self.session.flush()
        return int(aggregate.event_sequence or 0)

    def append_locked(
        self,
        aggregate: AgentSession,
        event_type: RuntimeEventType,
        *,
        run_id: str | None,
        payload: dict[str, Any],
        now: datetime,
        turn_id: str | None = None,
    ) -> None:
        aggregate.event_sequence = int(aggregate.event_sequence or 0) + 1
        item = payload.get("item")
        if isinstance(item, dict):
            self._upsert_run_item(
                aggregate=aggregate,
                item=item,
                run_id=run_id,
                now=now,
            )
        event_version = validate_runtime_event_payload(event_type, payload)
        self.session.add(
            AgentEventRecord(
                id=f"event_{uuid4().hex}",
                session_id=str(aggregate.id),
                run_id=run_id,
                turn_id=turn_id,
                sequence=int(aggregate.event_sequence or 0),
                type=event_type.value,
                event_version=event_version,
                payload_json=canonical_dumps(payload),
                created_at=now,
            )
        )
        self._compact(aggregate)
        pending = self.session.info.setdefault("dbfox_agent_event_sessions", set())
        pending.add(str(aggregate.id))

    def _upsert_run_item(
        self,
        *,
        aggregate: AgentSession,
        item: dict[str, Any],
        run_id: str | None,
        now: datetime,
    ) -> None:
        item_id = str(item.get("id") or "")
        if not item_id:
            raise ValueError("RunItem event payload is missing its id")
        record = self.session.get(AgentRunItemRecord, item_id)
        if record is None:
            item["sequence"] = int(aggregate.event_sequence or 0)
            record = AgentRunItemRecord(
                id=item_id,
                session_id=str(aggregate.id),
                run_id=str(item.get("run_id") or run_id or ""),
                turn_id=str(item["turn_id"]) if item.get("turn_id") else None,
                sequence=int(item["sequence"]),
                item_type=str(item.get("type") or ""),
                revision=int(item.get("revision") or 1),
                status=str(item.get("status") or ""),
                item_json="{}",
                created_at=datetime.fromisoformat(str(item["created_at"]).replace("Z", "+00:00")),
                updated_at=now,
                completed_at=(
                    datetime.fromisoformat(str(item["completed_at"]).replace("Z", "+00:00"))
                    if item.get("completed_at")
                    else None
                ),
            )
            self.session.add(record)
        else:
            self._update_run_item(record, aggregate, item, run_id, now)
        record.item_json = canonical_dumps(item)

    @staticmethod
    def _update_run_item(
        record: AgentRunItemRecord,
        aggregate: AgentSession,
        item: dict[str, Any],
        run_id: str | None,
        now: datetime,
    ) -> None:
        if str(record.session_id) != str(aggregate.id):
            raise ValueError("RunItem id is already owned by another Session")
        item_run_id = str(item.get("run_id") or run_id or "")
        if item_run_id != str(record.run_id):
            raise ValueError("RunItem run_id is immutable")
        item_type = str(item.get("type") or "")
        if item_type != str(record.item_type):
            raise ValueError("RunItem type is immutable")
        next_revision = int(item.get("revision") or record.revision or 0)
        if next_revision < int(record.revision or 0):
            raise ValueError("RunItem revision cannot regress")
        terminal_statuses = {"completed", "failed", "cancelled"}
        if str(record.status) in terminal_statuses and str(item.get("status") or "") != str(record.status):
            raise ValueError("Terminal RunItem status is immutable")
        item["sequence"] = int(record.sequence or 0)
        record.turn_id = str(item["turn_id"]) if item.get("turn_id") else record.turn_id
        record.revision = next_revision
        record.status = str(item.get("status") or record.status)
        record.updated_at = now
        record.completed_at = (
            datetime.fromisoformat(str(item["completed_at"]).replace("Z", "+00:00"))
            if item.get("completed_at")
            else None
        )

    def _compact(self, aggregate: AgentSession) -> None:
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

    def _session_for_update(self, session_id: str) -> AgentSession:
        aggregate = self.session.execute(
            select(AgentSession).where(AgentSession.id == session_id).with_for_update()
        ).scalar_one_or_none()
        if aggregate is None:
            raise KeyError(f"Unknown Agent Session: {session_id}")
        return aggregate

    @staticmethod
    def _require_lease(aggregate: AgentSession, lease: SessionLease) -> None:
        if aggregate.lease_owner != lease.owner or int(aggregate.lease_token or 0) != lease.token:
            raise SessionLeaseConflict("Session lease is no longer owned by this worker")

    @staticmethod
    def _require_run_lease(run: AgentRun, lease: SessionLease) -> None:
        if str(run.session_id) != lease.session_id or int(run.lease_token or 0) != lease.token:
            raise SessionLeaseConflict("Run is outside the active Session lease")
