import threading
import time
import pytest
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import sessionmaker

from engine.agent.coordinator import SessionCoordinator
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import SessionLeaseConflict
from engine.agent.session import SessionLease
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import AgentRun, AgentSession, AgentSessionInput


class RecordingLoop:
    def __init__(self, factory):
        self.factory = factory
        self.lock = threading.Lock()
        self.active_sessions = set()
        self.same_session_overlap = False
        self.max_parallel = 0
        self.calls = []

    def execute(self, *, lease, run_id, lease_lost=None):
        assert lease_lost is not None
        with self.lock:
            if lease.session_id in self.active_sessions:
                self.same_session_overlap = True
            self.active_sessions.add(lease.session_id)
            self.max_parallel = max(self.max_parallel, len(self.active_sessions))
            self.calls.append((lease.session_id, run_id))
        time.sleep(0.05)
        with self.factory() as db:
            run = db.get(AgentRun, run_id)
            admitted = db.get(AgentSessionInput, run.input_id)
            run.status = "completed"
            admitted.status = "consumed"
            db.commit()
        with self.lock:
            self.active_sessions.remove(lease.session_id)


def test_coordinator_serializes_session_and_parallelizes_independent_sessions(db_session, test_datasource):
    db_session.add_all([
        AgentSession(id="coordinator_a", title="A"),
        AgentSession(id="coordinator_b", title="B"),
    ])
    db_session.commit()
    sessions = SessionRepository(db_session)
    for key in ("a1", "a2"):
        sessions.admit(
            session_id="coordinator_a", resource_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version="1:1"),),
            content=key, idempotency_key=key, llm_credential_id="credential",
            api_base=None, model_name="model", request_payload={},
        )
    sessions.admit(
        session_id="coordinator_b", resource_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version="1:1"),),
        content="b1", idempotency_key="b1", llm_credential_id="credential",
        api_base=None, model_name="model", request_payload={},
    )
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    loop = RecordingLoop(factory)
    coordinator = SessionCoordinator(
        session_factory=factory, run_loop=loop, max_workers=3, lease_ttl_seconds=30,
    )
    coordinator.start()
    deadline = time.monotonic() + 3
    while len(loop.calls) < 3 and time.monotonic() < deadline:
        time.sleep(0.02)
    coordinator.stop()

    assert len(loop.calls) == 3
    assert loop.same_session_overlap is False
    assert loop.max_parallel >= 2
    assert [session for session, _ in loop.calls].count("coordinator_a") == 2


def test_heartbeat_retries_after_a_transient_storage_failure(monkeypatch):
    attempts = 0

    class ImmediateStop:
        stopped = False

        def wait(self, _delay):
            return self.stopped

        def set(self):
            self.stopped = True

    stop = ImmediateStop()

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            return None

    class FlakySessionRepository:
        def __init__(self, _db):
            pass

        def heartbeat(self, *, lease, ttl_seconds):
            nonlocal attempts
            assert lease.session_id == "heartbeat_session"
            assert ttl_seconds == 30
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary database interruption")
            stop.set()

    monkeypatch.setattr("engine.agent.coordinator.SessionRepository", FlakySessionRepository)
    coordinator = SessionCoordinator(
        session_factory=FakeDb,
        run_loop=object(),
        max_workers=1,
        lease_ttl_seconds=30,
    )
    lease = SessionLease(
        session_id="heartbeat_session",
        owner="worker",
        token=1,
        expires_at=datetime.now(UTC) + timedelta(seconds=30),
    )

    coordinator._heartbeat(lease, stop)

    assert attempts == 2


def test_heartbeat_signals_lease_loss(monkeypatch):
    class SingleTickStop:
        def __init__(self):
            self.calls = 0

        def wait(self, _delay):
            self.calls += 1
            return self.calls > 1

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class ConflictedSessionRepository:
        def __init__(self, _db):
            pass

        def heartbeat(self, *, lease, ttl_seconds):
            raise SessionLeaseConflict("lease lost")

    monkeypatch.setattr("engine.agent.coordinator.SessionRepository", ConflictedSessionRepository)
    coordinator = SessionCoordinator(
        session_factory=FakeDb,
        run_loop=object(),
        max_workers=1,
        lease_ttl_seconds=30,
    )
    lease = SessionLease(
        session_id="heartbeat_session",
        owner="worker",
        token=1,
        expires_at=datetime.now(UTC) + timedelta(seconds=30),
    )
    lease_lost = threading.Event()

    coordinator._heartbeat(lease, SingleTickStop(), lease_lost)

    assert lease_lost.is_set()


def test_finished_callback_cannot_remove_a_newer_session_worker() -> None:
    coordinator = SessionCoordinator(
        session_factory=object(),
        run_loop=object(),
        max_workers=1,
    )
    older: Future[None] = Future()
    newer: Future[None] = Future()
    from engine.agent.coordinator import _ActiveSession

    coordinator._active["session"] = _ActiveSession(newer, threading.Event())

    coordinator._finished("session", older)

    assert coordinator._active["session"].future is newer
    coordinator.stop(wait=False)


def test_wake_hints_are_bounded_without_creating_a_second_durable_queue() -> None:
    release = threading.Event()
    coordinator = SessionCoordinator(
        session_factory=object(),
        run_loop=object(),
        max_workers=1,
        max_scheduled_sessions=2,
    )

    def block(_session_id, _interrupt):
        release.wait(2)

    coordinator._drain_session = block  # type: ignore[method-assign]
    try:
        assert coordinator.wake("session-1") is True
        assert coordinator.wake("session-2") is True
        assert coordinator.wake("session-3") is False
        assert set(coordinator._active) == {"session-1", "session-2"}
        assert not hasattr(coordinator, "_pending")
    finally:
        release.set()
        coordinator.stop()


def test_scheduled_capacity_cannot_be_smaller_than_worker_capacity() -> None:
    with pytest.raises(ValueError, match="at least max_workers"):
        SessionCoordinator(
            session_factory=object(),
            run_loop=object(),
            max_workers=2,
            max_scheduled_sessions=1,
        )


def test_stop_interrupts_active_run_before_waiting_for_workers(db_session, test_datasource) -> None:
    session_id = "coordinator_shutdown"
    db_session.add(AgentSession(
        id=session_id,
        title="Shutdown",
    ))
    db_session.commit()
    SessionRepository(db_session).admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version="1:1"),),
        content="wait",
        idempotency_key="shutdown",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    class InterruptibleLoop:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.interrupted = threading.Event()
            self.closed = False

        def execute(self, *, lease, run_id, lease_lost=None):
            assert lease_lost is not None
            self.started.set()
            assert lease_lost.wait(2)
            self.interrupted.set()

        def close(self) -> None:
            self.closed = True

    loop = InterruptibleLoop()
    coordinator = SessionCoordinator(
        session_factory=factory,
        run_loop=loop,
        max_workers=1,
        lease_ttl_seconds=30,
    )
    coordinator.start()
    assert loop.started.wait(2)

    started = time.monotonic()
    coordinator.stop()

    assert time.monotonic() - started < 1
    assert loop.interrupted.is_set()
    assert loop.closed is True
