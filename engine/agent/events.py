"""Versioned public events and low-latency stream items for the Agent product."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from enum import StrEnum
from queue import Empty, Full, Queue
from threading import RLock
from typing import Any, Literal, TypeAlias
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class RuntimeEventType(StrEnum):
    SESSION_INPUT_ADMITTED = "session.input.admitted"
    SESSION_INPUT_PROMOTED = "session.input.promoted"
    SESSION_CONTEXT_UPDATED = "session.context.updated"
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_CANCELLING = "run.cancelling"
    RUN_CANCELLED = "run.cancelled"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    TURN_STARTED = "turn.started"
    TURN_COMPLETED = "turn.completed"
    ACTIVITY_UPDATED = "activity.updated"
    PLAN_UPDATED = "plan.updated"
    TOOL_REQUESTED = "tool.requested"
    TOOL_RUNNING = "tool.running"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    QUESTION_REQUESTED = "question.requested"
    QUESTION_RESOLVED = "question.resolved"
    OBSERVATION_CREATED = "observation.created"
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_UPDATED = "artifact.updated"
    ARTIFACT_SELECTED = "artifact.selected"
    ANSWER_COMPLETED = "answer.completed"


RuntimeEventCategory: TypeAlias = Literal[
    "session", "run", "turn", "activity", "plan", "tool", "approval", "question", "artifact", "answer"
]


class RuntimeEventContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    category: RuntimeEventCategory


_RUNTIME_EVENT_TYPES_BY_CATEGORY: dict[RuntimeEventCategory, tuple[RuntimeEventType, ...]] = {
    "session": (
        RuntimeEventType.SESSION_INPUT_ADMITTED,
        RuntimeEventType.SESSION_INPUT_PROMOTED,
        RuntimeEventType.SESSION_CONTEXT_UPDATED,
    ),
    "run": (
        RuntimeEventType.RUN_CREATED, RuntimeEventType.RUN_STARTED,
        RuntimeEventType.RUN_CANCELLING, RuntimeEventType.RUN_CANCELLED,
        RuntimeEventType.RUN_COMPLETED, RuntimeEventType.RUN_FAILED,
    ),
    "turn": (RuntimeEventType.TURN_STARTED, RuntimeEventType.TURN_COMPLETED),
    "activity": (RuntimeEventType.ACTIVITY_UPDATED,),
    "plan": (RuntimeEventType.PLAN_UPDATED,),
    "tool": (
        RuntimeEventType.TOOL_REQUESTED, RuntimeEventType.TOOL_RUNNING,
        RuntimeEventType.TOOL_COMPLETED, RuntimeEventType.TOOL_FAILED,
        RuntimeEventType.OBSERVATION_CREATED,
    ),
    "approval": (RuntimeEventType.APPROVAL_REQUESTED, RuntimeEventType.APPROVAL_RESOLVED),
    "question": (RuntimeEventType.QUESTION_REQUESTED, RuntimeEventType.QUESTION_RESOLVED),
    "artifact": (
        RuntimeEventType.ARTIFACT_CREATED, RuntimeEventType.ARTIFACT_UPDATED,
        RuntimeEventType.ARTIFACT_SELECTED,
    ),
    "answer": (RuntimeEventType.ANSWER_COMPLETED,),
}


RUNTIME_EVENT_CONTRACTS: dict[RuntimeEventType, RuntimeEventContract] = {
    event_type: RuntimeEventContract(version=1, category=category)
    for category, event_types in _RUNTIME_EVENT_TYPES_BY_CATEGORY.items()
    for event_type in event_types
}


_FORBIDDEN_DURABLE_RESULT_KEYS = frozenset({"rows", "previewRows", "preview_rows", "series"})


def validate_runtime_event_payload(event_type: RuntimeEventType, payload: dict[str, Any]) -> int:
    """Validate the public event boundary and return its declared schema version."""
    contract = RUNTIME_EVENT_CONTRACTS.get(event_type)
    if contract is None:
        raise ValueError(f"Runtime event has no registered contract: {event_type}")
    _reject_result_values(payload, path="payload")
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


class ActivityStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING = "waiting"
    CANCELLED = "cancelled"


class Activity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    title: str
    summary: str | None = None
    status: ActivityStatus
    tool_invocation_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None


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
    payload: dict[str, Any] = Field(default_factory=dict)

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
            payload=payload or {},
        )


LiveChannel = Literal["answer", "reasoning_summary", "tool_progress"]
LiveOperation = Literal["append", "replace"]


class LiveDelta(BaseModel):
    """Ephemeral hot-stream delta. Durable replay comes from RuntimeEventLog."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    run_id: str
    turn_id: str
    channel: LiveChannel
    operation: LiveOperation
    live_id: str
    channel_revision: int = Field(ge=1)
    correlation_id: str
    content: str


class RuntimeEventProjector:
    """The only boundary allowed to construct public RuntimeEvent payloads."""

    @staticmethod
    def activity(activity: Activity) -> dict[str, Any]:
        return {"activity": activity.model_dump(mode="json")}

    @staticmethod
    def entity(name: str, entity: BaseModel) -> dict[str, Any]:
        if name not in {
            "session_input",
            "run",
            "turn",
            "tool_invocation",
            "approval",
            "question",
            "observation",
            "artifact",
            "evidence",
            "answer",
            "response",
            "plan",
        }:
            raise ValueError(f"Unsupported public Agent entity: {name}")
        return {name: entity.model_dump(mode="json")}


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

    def receive(self, timeout: float | None = None) -> LiveDelta | None:
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
        self._snapshots: dict[str, LiveDelta] = {}
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

    def publish(self, delta: LiveDelta) -> bool:
        with self._lock:
            expected = self._revisions.get(delta.live_id, 0) + 1
            if delta.channel_revision < expected:
                return False
            if delta.channel_revision > expected:
                raise LiveStreamGap(
                    f"Live stream gap for {delta.live_id}: "
                    f"expected revision {expected}, got {delta.channel_revision}"
                )
            self._revisions[delta.live_id] = delta.channel_revision
            previous = self._snapshots.get(delta.live_id)
            content = (
                f"{previous.content if previous else ''}{delta.content}"
                if delta.operation == "append"
                else delta.content
            )
            self._snapshots[delta.live_id] = delta.model_copy(update={
                "operation": "replace",
                "content": content,
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
            prefix = f"live:"
            for live_id in [
                value for value in self._revisions
                if value.startswith(prefix) and f":{run_id}:" in value
            ]:
                self._revisions.pop(live_id, None)
                self._snapshots.pop(live_id, None)
        for subscription in subscribers:
            try:
                subscription._queue.put_nowait(_CLOSED)
            except Full:
                pass

    def _seed_subscription(
        self,
        subscription: LiveSubscription,
        snapshots: Iterable[LiveDelta],
    ) -> None:
        for snapshot in sorted(snapshots, key=lambda item: item.live_id):
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
    """Wake replay readers after a transaction commits; payload remains in SQL."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[CommitSubscription]] = {}
        self._generation: dict[str, int] = {}
        self._lock = RLock()

    def subscribe(self, session_id: str) -> CommitSubscription:
        subscription = CommitSubscription(self, session_id, Queue())
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
            subscription._queue.put_nowait(generation)


COMMIT_NOTIFICATIONS = CommitNotificationHub()
