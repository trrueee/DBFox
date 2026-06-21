from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import engine.agent_core.persistence_sink as sink_module
from engine.agent_core.persistence import get_conversation_detail
from engine.agent_core.types import (
    AgentArtifact,
    AgentArtifactPresentation,
    AgentRunRequest,
    AgentRuntimeEvent,
)
from engine.db import Base
from engine.models import AgentArtifactRecord, AgentRun, AgentRuntimeEventRecord, AgentSession, DataSource


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


def test_session_sink_records_artifacts_for_conversation_detail(tmp_path):
    db_path = tmp_path / "dbfox-meta-artifacts.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-artifacts",
            name="Artifact Test",
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
            question="Show registrations by user type.",
        )
        sink = sink_module.SessionPersistenceSink(db)
        sink.init_run_session(req, "run-artifacts", "session-artifacts")

        artifact = AgentArtifact(
            id="chart_suggestion_1",
            type="chart",
            title="Registrations by user type",
            payload={"series": [{"label": "personal_user", "value": 25}]},
            presentation=AgentArtifactPresentation(mode="inline", priority=80),
            depends_on=["result_table_1"],
        )
        event = AgentRuntimeEvent(
            event_id="runtime_artifacts_1_tool_completed",
            run_id="run-artifacts",
            session_id="session-artifacts",
            sequence=2,
            created_at_ms=2,
            type="agent.step.completed",
            step={"name": "tools", "tool_name": "sql.execute_readonly", "status": "completed"},
        )
        sink.record_event("session-artifacts", event)
        sink.record_artifact("session-artifacts", "run-artifacts", artifact, 3)
        db.commit()

        records = db.query(AgentArtifactRecord).all()
        detail = get_conversation_detail(db, "session-artifacts")

        assert [record.id for record in records] == ["chart_suggestion_1"]
        assert detail is not None
        assert len(detail["artifacts"]) == 1
        assert detail["artifacts"][0]["message_id"] == detail["runs"][0]["assistant_message_id"]
        assert detail["artifacts"][0]["depends_on"] == ["result_table_1"]
        assert detail["runs"][0]["events"][0]["type"] == "agent.step.completed"
        assert detail["runs"][0]["events"][0]["step"]["tool_name"] == "sql.execute_readonly"
    finally:
        db.close()
        engine.dispose()


def test_conversation_detail_recovers_response_json_artifacts_without_migration(tmp_path):
    db_path = tmp_path / "dbfox-meta-response-artifacts.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-response-artifacts",
            name="Response Artifact Test",
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
            question="Recover chart artifacts from response JSON.",
        )
        sink = sink_module.SessionPersistenceSink(db)
        sink.init_run_session(req, "run-response-artifacts", "session-response-artifacts")

        run = db.get(AgentRun, "run-response-artifacts")
        assert run is not None
        run.status = "completed"
        run.response_json = json.dumps(
            {
                "artifacts": [
                    {
                        "id": "chart_from_response",
                        "type": "chart",
                        "title": "Recovered chart",
                        "payload": {"series": [{"label": "personal_user", "value": 25}]},
                        "presentation": {"mode": "inline", "priority": 80},
                        "depends_on": ["result_table_from_response"],
                    }
                ]
            }
        )
        db.commit()

        assert db.query(AgentArtifactRecord).count() == 0
        detail = get_conversation_detail(db, "session-response-artifacts")

        assert detail is not None
        assert len(detail["artifacts"]) == 1
        assert detail["artifacts"][0]["id"] == "chart_from_response"
        assert detail["artifacts"][0]["message_id"] == detail["runs"][0]["assistant_message_id"]
        assert detail["artifacts"][0]["depends_on"] == ["result_table_from_response"]
    finally:
        db.close()
        engine.dispose()
