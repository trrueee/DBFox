"""Versioned public events and low-latency stream items for the Agent product."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from enum import StrEnum
from queue import Empty, Full, Queue
from threading import RLock
from typing import Any, Literal, TypeAlias
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from engine.agent.run_item import RunItem, RunItemDelta, RunProjection


class RuntimeEventType(StrEnum):
    RUN_STARTED = "run.started"
    RUN_UPDATED = "run.updated"
    RUN_CANCELLED = "run.cancelled"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_ITEM_STARTED = "run.item.started"
    RUN_ITEM_UPDATED = "run.item.updated"
    RUN_ITEM_COMPLETED = "run.item.completed"
    RUN_ITEM_FAILED = "run.item.failed"
    RUN_ITEM_CANCELLED = "run.item.cancelled"


RuntimeEventCategory: TypeAlias = Literal["run", "item"]


class RuntimeEventContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    category: RuntimeEventCategory


_RUNTIME_EVENT_TYPES_BY_CATEGORY: dict[RuntimeEventCategory, tuple[RuntimeEventType, ...]] = {
    "run": (
        RuntimeEventType.RUN_STARTED, RuntimeEventType.RUN_UPDATED,
        RuntimeEventType.RUN_CANCELLED,
        RuntimeEventType.RUN_COMPLETED, RuntimeEventType.RUN_FAILED,
    ),
    "item": (
        RuntimeEventType.RUN_ITEM_STARTED,
        RuntimeEventType.RUN_ITEM_UPDATED,
        RuntimeEventType.RUN_ITEM_COMPLETED,
        RuntimeEventType.RUN_ITEM_FAILED,
        RuntimeEventType.RUN_ITEM_CANCELLED,
    ),
}


RUNTIME_EVENT_CONTRACTS: dict[RuntimeEventType, RuntimeEventContract] = {
    event_type: RuntimeEventContract(version=1, category=category)
    for category, event_types in _RUNTIME_EVENT_TYPES_BY_CATEGORY.items()
    for event_type in event_types
}


_FORBIDDEN_DURABLE_RESULT_KEYS = frozenset({"rows", "previewRows", "preview_rows", "series"})
_RUN_ITEM_ADAPTER: TypeAdapter[RunItem] = TypeAdapter(RunItem)


def validate_runtime_event_payload(event_type: RuntimeEventType, payload: dict[str, Any]) -> int:
    """Validate the public event boundary and return its declared schema version."""
    contract = RUNTIME_EVENT_CONTRACTS.get(event_type)
    if contract is None:
        raise ValueError(f"Runtime event has no registered contract: {event_type}")
    _reject_result_values(payload, path="payload")
    if contract.category == "item":
        item = payload.get("item")
        if not isinstance(item, dict):
            raise ValueError("RunItem event payload must contain one canonical item")
        _RUN_ITEM_ADAPTER.validate_python(item)
    return contract.version


def _reject_result_values(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _FORBIDDEN_DURABLE_RESULT_KEYS and child not in (None, [], {}):
                raise ValueError(f"Runtime event cannot persist result values at {path}.{key}")
            _reject_result_values(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_result_values(child, path=f"{path}[{index}]")


class RuntimeEvent(BaseModel):
    """Committed event ordered by the owning Session aggregate."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: RuntimeEventType
    event_version: int = Field(default=1, ge=1)
    session_id: str
    run_id: str | None = None
    turn_id: str | None = None
    sequence: int = Field(ge=1)
    timestamp: datetime
    payload: "RuntimeEventPayload" = Field(default_factory=lambda: RuntimeEventPayload())

    @classmethod
    def create(
        cls,
        *,
        event_type: RuntimeEventType,
        session_id: str,
        sequence: int,
        run_id: str | None = None,
        turn_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "RuntimeEvent":
        return cls(
            event_id=f"event_{uuid4().hex}",
            event_type=event_type,
            session_id=session_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=datetime.now(timezone.utc),
            payload=RuntimeEventPayload.model_validate(payload or {}),
        )


class RuntimeEventPayload(BaseModel):
    """Typed event projection; durable event writers still submit plain dictionaries."""

    model_config = ConfigDict(extra="forbid")

    run: RunProjection | None = None
    item: RunItem | None = None


RuntimeEvent.model_rebuild()


class LiveStreamGap(RuntimeError):
    """A subscriber fell behind and must recover from the durable snapshot."""


_CLOSED = object()
_GAP = object()


class LiveSubscription:
    def __init__(
        self, *, hub: "LiveStreamHub", run_id: str | None,
        session_id: str | None, queue: Queue[Any],
    ) -> None:
        self._hub = hub
        self.run_id = run_id
        self.session_id = session_id
        self._queue = queue
        self._closed = False

    def receive(self, timeout: float | None = None) -> RunItemDelta | None:
        try:
            value = self._queue.get(timeout=timeout)
        except Empty:
            return None
        if value is _GAP:
            self.close()
            raise LiveStreamGap("Live stream subscriber overflowed; reload the durable snapshot")
        if value is _CLOSED:
            self.close()
            return None
        return value

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._hub.unsubscribe(self)

    def __enter__(self) -> "LiveSubscription":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class LiveStreamHub:
    """Process-local low-latency fanout; durable state remains in repositories."""

    def __init__(self, *, subscriber_capacity: int = 2048) -> None:
        self._capacity = subscriber_capacity
        self._subscribers: dict[str, set[LiveSubscription]] = {}
        self._session_subscribers: dict[str, set[LiveSubscription]] = {}
        self._revisions: dict[str, int] = {}
        self._snapshots: dict[str, RunItemDelta] = {}
        self._lock = RLock()

    def subscribe(self, run_id: str) -> LiveSubscription:
        subscription = LiveSubscription(
            hub=self,
            run_id=run_id,
            session_id=None,
            queue=Queue(maxsize=self._capacity),
        )
        with self._lock:
            self._subscribers.setdefault(run_id, set()).add(subscription)
            self._seed_subscription(
                subscription,
                (
                    snapshot for snapshot in self._snapshots.values()
                    if snapshot.run_id == run_id
                ),
            )
        return subscription

    def subscribe_session(self, session_id: str) -> LiveSubscription:
        subscription = LiveSubscription(
            hub=self, run_id=None, session_id=session_id,
            queue=Queue(maxsize=self._capacity),
        )
        with self._lock:
            self._session_subscribers.setdefault(session_id, set()).add(subscription)
            self._seed_subscription(
                subscription,
                (
                    snapshot for snapshot in self._snapshots.values()
                    if snapshot.session_id == session_id
                ),
            )
        return subscription

    def unsubscribe(self, subscription: LiveSubscription) -> None:
        with self._lock:
            if subscription.run_id is not None:
                subscribers = self._subscribers.get(subscription.run_id)
                if subscribers is not None:
                    subscribers.discard(subscription)
                    if not subscribers:
                        self._subscribers.pop(subscription.run_id, None)
            if subscription.session_id is not None:
                subscribers = self._session_subscribers.get(subscription.session_id)
                if subscribers is not None:
                    subscribers.discard(subscription)
                    if not subscribers:
                        self._session_subscribers.pop(subscription.session_id, None)

    def publish(self, delta: RunItemDelta) -> bool:
        with self._lock:
            expected = self._revisions.get(delta.item_id, 0) + 1
            if delta.revision < expected:
                return False
            if delta.revision > expected:
                raise LiveStreamGap(
                    f"Live stream gap for {delta.item_id}: "
                    f"expected revision {expected}, got {delta.revision}"
                )
            previous = self._snapshots.get(delta.item_id)
            expected_offset = len(previous.content) if previous else 0
            if delta.offset != expected_offset:
                raise LiveStreamGap(
                    f"Live stream offset gap for {delta.item_id}: "
                    f"expected offset {expected_offset}, got {delta.offset}"
                )
            self._revisions[delta.item_id] = delta.revision
            self._snapshots[delta.item_id] = delta.model_copy(update={
                "offset": 0,
                "content": f"{previous.content if previous else ''}{delta.content}",
            })
            subscribers = tuple({
                *self._subscribers.get(delta.run_id, ()),
                *self._session_subscribers.get(delta.session_id, ()),
            })
        for subscription in subscribers:
            try:
                subscription._queue.put_nowait(delta)
            except Full:
                try:
                    subscription._queue.get_nowait()
                    subscription._queue.put_nowait(_GAP)
                except (Empty, Full):
                    pass
        return True

    def close_run(self, run_id: str) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers.pop(run_id, ()))
            for item_id, snapshot in list(self._snapshots.items()):
                if snapshot.run_id == run_id:
                    self._revisions.pop(item_id, None)
                    self._snapshots.pop(item_id, None)
        for subscription in subscribers:
            try:
                subscription._queue.put_nowait(_CLOSED)
            except Full:
                pass

    def _seed_subscription(
        self,
        subscription: LiveSubscription,
        snapshots: Iterable[RunItemDelta],
    ) -> None:
        for snapshot in sorted(snapshots, key=lambda item: item.item_id):
            try:
                subscription._queue.put_nowait(snapshot)
            except Full:
                try:
                    subscription._queue.get_nowait()
                    subscription._queue.put_nowait(_GAP)
                except (Empty, Full):
                    pass
                return


class CommitSubscription:
    def __init__(self, hub: "CommitNotificationHub", session_id: str, queue: Queue[int]) -> None:
        self._hub = hub
        self.session_id = session_id
        self._queue = queue
        self._closed = False

    def receive(self, timeout: float | None = None) -> int | None:
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._hub.unsubscribe(self)


class CommitNotificationHub:
    """Coalesced wakeups for replay readers; payload remains in durable SQL."""

    def __init__(self, *, subscriber_capacity: int = 1) -> None:
        self._capacity = max(1, subscriber_capacity)
        self._subscribers: dict[str, set[CommitSubscription]] = {}
        self._generation: dict[str, int] = {}
        self._lock = RLock()

    def subscribe(self, session_id: str) -> CommitSubscription:
        subscription = CommitSubscription(
            self,
            session_id,
            Queue(maxsize=self._capacity),
        )
        with self._lock:
            self._subscribers.setdefault(session_id, set()).add(subscription)
        return subscription

    def unsubscribe(self, subscription: CommitSubscription) -> None:
        with self._lock:
            values = self._subscribers.get(subscription.session_id)
            if values:
                values.discard(subscription)
                if not values:
                    self._subscribers.pop(subscription.session_id, None)

    def publish(self, session_id: str) -> None:
        with self._lock:
            generation = self._generation.get(session_id, 0) + 1
            self._generation[session_id] = generation
            subscribers = tuple(self._subscribers.get(session_id, ()))
        for subscription in subscribers:
            try:
                subscription._queue.put_nowait(generation)
            except Full:
                # A commit notification is only a wakeup. Replace the stale
                # generation instead of accumulating one item per transaction.
                try:
                    subscription._queue.get_nowait()
                    subscription._queue.put_nowait(generation)
                except (Empty, Full):
                    pass


COMMIT_NOTIFICATIONS = CommitNotificationHub()
