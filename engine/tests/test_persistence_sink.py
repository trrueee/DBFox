from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import engine.agent_core.persistence_sink as sink_module
from engine.agent_core.types import AgentRunRequest, AgentRuntimeEvent
from engine.db import Base
from engine.models import AgentRun, AgentRuntimeEventRecord, AgentSession, DataSource


def test_default_persistence_sink_shares_caller_session_when_sqlite_is_locked(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("AGENT_PERSISTENCE_MODE", raising=False)
    monkeypatch.delenv("DBFOX_TESTING", raising=False)

    db_path = tmp_path / "dbfox-meta.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 0.05},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(sink_module, "SessionLocal", TestSessionLocal)

    main_db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-lock",
            name="Lock Test",
            db_type="sqlite",
            host="localhost",
            port=0,
            database_name=str(db_path),
            username="",
            password_ciphertext="",
            password_nonce="",
            password_key_version="v1",
            status="active",
        )
        session = AgentSession(
            id="session-lock",
            datasource_id=datasource.id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        run = AgentRun(
            id="run-lock",
            session_id=session.id,
            datasource_id=datasource.id,
            question="Can runtime events persist while the caller has a write transaction?",
            status="running",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        main_db.add_all([datasource, session, run])
        main_db.flush()

        sink = sink_module.create_persistence_sink(main_db)
        event = AgentRuntimeEvent(
            event_id="runtime_lock_1_agent_run_started",
            run_id=run.id,
            session_id=session.id,
            sequence=1,
            created_at_ms=1,
            type="agent.run.started",
            step={"question": run.question},
        )

        sink.record_event(session.id, event)
        main_db.commit()
    finally:
        main_db.close()

    verify_db = TestSessionLocal()
    try:
        records = verify_db.query(AgentRuntimeEventRecord).all()
        assert [record.id for record in records] == [event.event_id]
    finally:
        verify_db.close()
        engine.dispose()


def test_session_sink_initializes_the_resolved_session_id(tmp_path):
    db_path = tmp_path / "dbfox-meta-session.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-resolved",
            name="Resolved Session Test",
            db_type="sqlite",
            host="localhost",
            port=0,
            database_name=str(db_path),
            username="",
            password_ciphertext="",
            password_nonce="",
            password_key_version="v1",
            status="active",
        )
        db.add(datasource)
        db.flush()

        req = AgentRunRequest(
            datasource_id=datasource.id,
            question="Create the run under the resolved session id.",
        )
        sink = sink_module.SessionPersistenceSink(db)

        sink.init_run_session(req, "run-resolved", "session-resolved")
        db.commit()

        persisted_session = (
            db.query(AgentSession)
            .filter(AgentSession.id == "session-resolved")
            .first()
        )
        persisted_run = db.query(AgentRun).filter(AgentRun.id == "run-resolved").first()

        assert persisted_session is not None
        assert persisted_run is not None
        assert persisted_run.session_id == persisted_session.id
    finally:
        db.close()
        engine.dispose()
