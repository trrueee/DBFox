import queue
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.events import CommitNotificationHub
from engine.agent.events import RuntimeEventType
from engine.agent.repositories.events import EventRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.run_item import RunItemDelta, RunItemType
from engine.api import conversation_stream


class FakeSubscription:
    def __init__(self, values=None):
        self.values = queue.Queue()
        for value in values or []:
            self.values.put(value)
        self.closed = False

    def receive(self, timeout):
        if self.closed:
            return None
        try:
            return self.values.get(timeout=min(timeout, 0.01))
        except queue.Empty:
            return None

    def close(self):
        self.closed = True


def test_sse_catches_up_all_precommitted_pages_before_waiting(db_session, monkeypatch):
    sessions = SessionRepository(db_session)
    session = sessions.create(project_id=None, title="backlog")
    admission = sessions.admit(session_id=session.id, resource_refs=(), content="synthetic",
                               idempotency_key="first", llm_credential_id="synthetic",
                               api_base=None, model_name=None, request_payload={})
    events = EventRepository(db_session)
    original = events.list(session.id, limit=1)[0]
    for _ in range(1199):
        events.append_locked(session, RuntimeEventType.RUN_UPDATED, run_id=admission.run_id,
                             payload=original.payload.model_dump(mode="json", exclude_none=True),
                             now=datetime.now(UTC))
    db_session.commit()
    count = len(events.list(session.id, limit=2000))
    monkeypatch.setattr(conversation_stream, "SessionLocal", sessionmaker(bind=db_session.get_bind()))
    original_queue = queue.Queue

    class NoPrematureWait(original_queue):
        def get(self, block=True, timeout=None):
            if timeout == 15.0:
                raise AssertionError("SSE waited while committed backlog was unread")
            return super().get(block=block, timeout=timeout)

    monkeypatch.setattr(conversation_stream.queue, "Queue", NoPrematureWait)
    stream = conversation_stream.conversation_stream(session.id, 0)
    try:
        frames = [next(stream) for _ in range(count)]
        assert count > 1000
        assert all(frame.startswith("id:") for frame in frames)
        assert frames[-1].startswith(f"id: {count}\n")
    finally:
        stream.close()


class FakeHub:
    def __init__(self, subscription):
        self.subscription = subscription

    def subscribe(self, _session_id):
        return self.subscription

    def subscribe_session(self, _session_id):
        return self.subscription


class FakeDb:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeEventRepository:
    def __init__(self, _db):
        pass

    def list(self, _session_id, *, after_sequence, limit):
        return []


def test_commit_notifications_are_bounded_and_coalesce_to_latest_generation():
    hub = CommitNotificationHub(subscriber_capacity=1)
    subscription = hub.subscribe("session-1")

    for _ in range(10_000):
        hub.publish("session-1")

    assert subscription.receive(timeout=0.01) == 10_000
    assert subscription.receive(timeout=0.01) is None
    subscription.close()


def test_sse_multiplexer_closes_on_bounded_live_queue_overflow(monkeypatch):
    live_values = [
        RunItemDelta(
            session_id="session-1",
            run_id="run-1",
            turn_id="turn-1",
            item_id="answer:run-1:turn-1",
            item_type=RunItemType.MESSAGE,
            field="content",
            revision=index + 1,
            offset=index,
            content="x",
        )
        for index in range(700)
    ]
    commit_subscription = FakeSubscription()
    live_subscription = FakeSubscription(live_values)
    monkeypatch.setattr(
        conversation_stream,
        "COMMIT_NOTIFICATIONS",
        FakeHub(commit_subscription),
    )
    monkeypatch.setattr(
        conversation_stream,
        "LIVE_STREAM_HUB",
        FakeHub(live_subscription),
    )
    monkeypatch.setattr(conversation_stream, "SessionLocal", FakeDb)
    monkeypatch.setattr(conversation_stream, "EventRepository", FakeEventRepository)

    stream = conversation_stream.conversation_stream("session-1", 0)
    # Depending on scheduling, overflow may be detected before the consumer
    # sees the first delta or immediately afterward. Either way, a stream gap
    # must close the connection instead of exposing an incomplete projection.
    try:
        next(stream)
    except StopIteration:
        pass
    else:
        time.sleep(0.05)
        with pytest.raises(StopIteration):
            next(stream)

    assert commit_subscription.closed is True
    assert live_subscription.closed is True
