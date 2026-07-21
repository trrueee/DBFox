import threading
import time

from sqlalchemy.orm import sessionmaker

from engine.agent.coordinator import SessionCoordinator
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentRun, AgentSession, AgentSessionInput


class RecordingLoop:
    def __init__(self, factory):
        self.factory = factory
        self.lock = threading.Lock()
        self.active_sessions = set()
        self.same_session_overlap = False
        self.max_parallel = 0
        self.calls = []

    def execute(self, *, lease, run_id):
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
        AgentSession(id="coordinator_a", datasource_id=str(test_datasource.id), title="A"),
        AgentSession(id="coordinator_b", datasource_id=str(test_datasource.id), title="B"),
    ])
    db_session.commit()
    sessions = SessionRepository(db_session)
    for key in ("a1", "a2"):
        sessions.admit(
            session_id="coordinator_a", datasource_id=str(test_datasource.id), datasource_generation=1,
            content=key, idempotency_key=key, llm_credential_id="credential",
            api_base=None, model_name="model", request_payload={},
        )
    sessions.admit(
        session_id="coordinator_b", datasource_id=str(test_datasource.id), datasource_generation=1,
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
