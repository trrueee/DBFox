from __future__ import annotations

import json
import importlib.util
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import engine.agent_core.event_store as event_store_module
from engine.agent_core import persistence as agent_persistence
from engine.agent_core.persistence import get_conversation_detail
from engine.agent_core.types import (
    AgentArtifact,
    AgentArtifactPresentation,
    AgentRunRequest,
    AgentRuntimeEvent,
)
from engine.db import Base
from engine.models import (
    AgentArtifactRecord,
    AgentCheckpoint,
    AgentRun,
    AgentRuntimeEventRecord,
    AgentSession,
    DataSource,
)


def test_legacy_persistence_sink_module_is_removed():
    assert importlib.util.find_spec("engine.agent_core.persistence_sink") is None


def test_default_agent_event_store_shares_caller_session_when_sqlite_is_locked(
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

        store = event_store_module.create_agent_event_store(main_db)
        event = AgentRuntimeEvent(
            event_id="runtime_lock_1_agent_run_started",
            run_id=run.id,
            session_id=session.id,
            sequence=1,
            created_at_ms=1,
            type="agent.run.started",
            step={"question": run.question},
        )

        store.append_event(session.id, event)
        store.flush()
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


def test_sqlite_agent_event_store_initializes_the_resolved_session_id(tmp_path):
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
        store = event_store_module.SQLiteAgentEventStore(db)

        store.start_run(req, run_id="run-resolved", session_id="session-resolved")
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


def test_sqlite_agent_event_store_records_artifacts_for_conversation_detail(tmp_path):
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
        store = event_store_module.SQLiteAgentEventStore(db)
        store.start_run(req, run_id="run-artifacts", session_id="session-artifacts")

        artifact = AgentArtifact(
            id="chart_suggestion_1",
            type="chart",
            title="Registrations by user type",
            payload={"series": [{"label": "personal_user", "value": 25}]},
            presentation=AgentArtifactPresentation(mode="inline", priority=80),
            depends_on=["result_view_1"],
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
        store.append_event("session-artifacts", event)
        store.append_artifact("session-artifacts", "run-artifacts", artifact, 3)
        db.commit()

        records = db.query(AgentArtifactRecord).all()
        detail = get_conversation_detail(db, "session-artifacts")

        assert [record.id for record in records] == ["chart_suggestion_1"]
        assert detail is not None
        assert len(detail["artifacts"]) == 1
        assert detail["artifacts"][0]["message_id"] == detail["runs"][0]["assistant_message_id"]
        assert detail["artifacts"][0]["depends_on"] == ["result_view_1"]
        assert detail["runs"][0]["events"][0]["type"] == "agent.step.completed"
        assert detail["runs"][0]["events"][0]["step"]["tool_name"] == "sql.execute_readonly"
    finally:
        db.close()
        engine.dispose()


def test_sqlite_agent_event_store_saves_checkpoint_and_marks_run_waiting_approval(tmp_path):
    db_path = tmp_path / "dbfox-meta-checkpoint.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-checkpoint",
            name="Checkpoint Test",
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
            question="Need approval before executing SQL.",
        )
        store = event_store_module.SQLiteAgentEventStore(db)
        store.start_run(req, run_id="run-checkpoint", session_id="session-checkpoint")
        approval = agent_persistence.create_approval(
            db,
            run_id="run-checkpoint",
            session_id="session-checkpoint",
            step_name="sql.execute_readonly",
            tool_name="sql.execute_readonly",
            risk_level="warning",
            reason="requires approval",
            policy_decision={"requires_confirmation": True},
            requested_action={"tool_name": "sql.execute_readonly", "args": {"sql": "SELECT 1"}},
        )

        checkpoint = store.save_checkpoint(
            run_id="run-checkpoint",
            session_id="session-checkpoint",
            status="waiting_approval",
            current_step_name=approval.step_name,
            next_step_name=approval.step_name,
            plan={"steps": ["approve"]},
            state={"pending_approval": approval.model_dump(mode="json")},
            completed_steps=[{"name": "validate"}],
            pending_steps=[{"name": approval.step_name}],
            artifacts=[],
            waiting_approval_id=approval.id,
        )
        db.commit()

        run = db.get(AgentRun, "run-checkpoint")
        saved_checkpoint = db.query(AgentCheckpoint).filter(
            AgentCheckpoint.run_id == "run-checkpoint"
        ).one()

        assert checkpoint is not None
        assert checkpoint.id == saved_checkpoint.id
        assert run is not None
        assert run.status == "waiting_approval"
        assert run.current_step_name == "sql.execute_readonly"
        assert run.waiting_approval_id == approval.id
    finally:
        db.close()
        engine.dispose()


def test_buffered_agent_event_store_flushes_runtime_events(tmp_path):
    from engine.agent_core.event_store import BufferedAgentEventStore, SQLiteAgentEventStore

    db_path = tmp_path / "dbfox-meta-event-store.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-event-store",
            name="Event Store Test",
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
            question="Buffer events.",
        )
        store = BufferedAgentEventStore(SQLiteAgentEventStore(db), flush_every=2)
        store.start_run(req, run_id="run-event-store", session_id="session-event-store")

        first = AgentRuntimeEvent(
            event_id="runtime_buffered_1",
            run_id="run-event-store",
            session_id="session-event-store",
            sequence=1,
            created_at_ms=1,
            type="agent.run.started",
            step={"question": "Buffer events."},
        )
        second = AgentRuntimeEvent(
            event_id="runtime_buffered_2",
            run_id="run-event-store",
            session_id="session-event-store",
            sequence=2,
            created_at_ms=2,
            type="agent.step.completed",
            step={"name": "observe", "status": "completed"},
        )

        store.append_event("session-event-store", first)
        assert db.query(AgentRuntimeEventRecord).count() == 0

        store.append_event("session-event-store", second)
        db.commit()

        records = (
            db.query(AgentRuntimeEventRecord)
            .filter(AgentRuntimeEventRecord.run_id == "run-event-store")
            .order_by(AgentRuntimeEventRecord.sequence)
            .all()
        )
        assert [record.id for record in records] == ["runtime_buffered_1", "runtime_buffered_2"]
    finally:
        db.close()
        engine.dispose()


def test_buffered_agent_event_store_flushes_checkpoint_and_returns_record(tmp_path):
    from engine.agent_core.event_store import BufferedAgentEventStore, SQLiteAgentEventStore

    db_path = tmp_path / "dbfox-meta-buffered-checkpoint.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-buffered-checkpoint",
            name="Buffered Checkpoint Test",
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
            question="Buffer checkpoint.",
        )
        store = BufferedAgentEventStore(SQLiteAgentEventStore(db), flush_every=10)
        store.start_run(req, run_id="run-buffered-checkpoint", session_id="session-buffered-checkpoint")

        checkpoint = store.save_checkpoint(
            run_id="run-buffered-checkpoint",
            session_id="session-buffered-checkpoint",
            status="waiting_approval",
            current_step_name="approval_interrupt",
            next_step_name="approval_interrupt",
            plan=None,
            state={"status": "waiting_approval"},
            completed_steps=[],
            pending_steps=[{"name": "approval_interrupt"}],
            artifacts=[],
        )
        db.commit()

        assert checkpoint is not None
        assert db.query(AgentRun).filter(AgentRun.id == "run-buffered-checkpoint").count() == 1
        assert db.query(AgentCheckpoint).filter(AgentCheckpoint.id == checkpoint.id).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_sqlite_agent_event_store_cancels_run(tmp_path):
    db_path = tmp_path / "dbfox-meta-cancel.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-cancel",
            name="Cancel Test",
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
            question="Cancel this run.",
        )
        store = event_store_module.SQLiteAgentEventStore(db)
        store.start_run(req, run_id="run-cancel", session_id="session-cancel")

        store.cancel_run("run-cancel")
        db.commit()

        run = db.get(AgentRun, "run-cancel")
        assert run is not None
        assert run.status == "cancelled"
        assert run.waiting_approval_id is None
    finally:
        db.close()
        engine.dispose()


def test_buffered_agent_event_store_flushes_start_before_cancel(tmp_path):
    from engine.agent_core.event_store import BufferedAgentEventStore, SQLiteAgentEventStore

    db_path = tmp_path / "dbfox-meta-buffered-cancel.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-buffered-cancel",
            name="Buffered Cancel Test",
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
            question="Buffer then cancel.",
        )
        store = BufferedAgentEventStore(SQLiteAgentEventStore(db), flush_every=10)
        store.start_run(req, run_id="run-buffered-cancel", session_id="session-buffered-cancel")

        store.cancel_run("run-buffered-cancel")
        db.commit()

        run = db.get(AgentRun, "run-buffered-cancel")
        assert run is not None
        assert run.status == "cancelled"
    finally:
        db.close()
        engine.dispose()


def test_sqlite_agent_event_store_resolves_approval_and_marks_run_resumed(tmp_path):
    db_path = tmp_path / "dbfox-meta-resume.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-resume",
            name="Resume Test",
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
            question="Resume after approval.",
        )
        store = event_store_module.SQLiteAgentEventStore(db)
        store.start_run(req, run_id="run-resume", session_id="session-resume")
        approval = agent_persistence.create_approval(
            db,
            run_id="run-resume",
            session_id="session-resume",
            step_name="sql.execute_readonly",
            tool_name="sql.execute_readonly",
            risk_level="warning",
            reason="requires approval",
            policy_decision={"requires_confirmation": True},
            requested_action={"tool_name": "sql.execute_readonly", "args": {"sql": "SELECT 1"}},
        )
        store.save_checkpoint(
            run_id="run-resume",
            session_id="session-resume",
            status="waiting_approval",
            current_step_name=approval.step_name,
            next_step_name=approval.step_name,
            plan=None,
            state={"pending_approval": approval.model_dump(mode="json")},
            completed_steps=[],
            pending_steps=[{"name": approval.step_name}],
            artifacts=[],
            waiting_approval_id=approval.id,
        )

        resolved = store.resolve_approval(
            run_id="run-resume",
            approval_id=approval.id,
            decision="approved",
            note="ok",
        )
        store.mark_run_resumed("run-resume")
        db.commit()

        run = db.get(AgentRun, "run-resume")
        saved_approval = agent_persistence.get_approval(db, approval.id)
        assert resolved is not None
        assert resolved.status == "approved"
        assert saved_approval is not None
        assert saved_approval.status == "approved"
        assert saved_approval.decision_note == "ok"
        assert run is not None
        assert run.status == "running"
        assert run.waiting_approval_id is None
    finally:
        db.close()
        engine.dispose()


def test_sqlite_agent_event_store_creates_approval(tmp_path):
    db_path = tmp_path / "dbfox-meta-create-approval.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-create-approval",
            name="Create Approval Test",
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
            question="Create approval.",
        )
        store = event_store_module.SQLiteAgentEventStore(db)
        store.start_run(req, run_id="run-create-approval", session_id="session-create-approval")

        approval = store.create_approval(
            run_id="run-create-approval",
            session_id="session-create-approval",
            step_name="sql.execute_readonly",
            tool_name="sql.execute_readonly",
            risk_level="warning",
            reason="requires approval",
            policy_decision={"requires_confirmation": True},
            requested_action={"tool_name": "sql.execute_readonly", "args": {"sql": "SELECT 1"}},
        )
        db.commit()

        saved = agent_persistence.get_approval(db, approval.id)
        assert saved is not None
        assert saved.status == "pending"
        assert saved.run_id == "run-create-approval"
        assert saved.requested_action == {"tool_name": "sql.execute_readonly", "args": {"sql": "SELECT 1"}}
    finally:
        db.close()
        engine.dispose()


def test_approval_checkpoint_draft_does_not_write_metadata(tmp_path):
    from engine.agent.app.persistence import build_approval_checkpoint_draft

    db_path = tmp_path / "dbfox-meta-approval-draft.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-approval-draft",
            name="Approval Draft Test",
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
            question="Draft approval checkpoint.",
        )
        store = event_store_module.SQLiteAgentEventStore(db)
        store.start_run(req, run_id="run-approval-draft", session_id="session-approval-draft")
        approval = agent_persistence.create_approval(
            db,
            run_id="run-approval-draft",
            session_id="session-approval-draft",
            step_name="sql.execute_readonly",
            tool_name="sql.execute_readonly",
            risk_level="warning",
            reason="requires approval",
            policy_decision={"requires_confirmation": True},
            requested_action={"tool_name": "sql.execute_readonly", "args": {"sql": "SELECT 1"}},
        )
        db.flush()

        draft = build_approval_checkpoint_draft(
            run_id="run-approval-draft",
            session_id="session-approval-draft",
            req=req,
            full_state={
                "status": "waiting_approval",
                "pending_approval": approval.model_dump(mode="json"),
            },
            steps=[],
            artifacts=[],
        )

        run = db.get(AgentRun, "run-approval-draft")
        assert draft.approval is not None
        assert draft.approval.id == approval.id
        assert db.query(AgentCheckpoint).filter(AgentCheckpoint.run_id == "run-approval-draft").count() == 0
        assert run is not None
        assert run.status == "running"
        assert run.waiting_approval_id is None
    finally:
        db.close()
        engine.dispose()


def test_buffered_agent_event_store_factory_delays_until_flush(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_PERSISTENCE_MODE", "buffered")
    monkeypatch.setenv("AGENT_PERSISTENCE_FLUSH_EVERY", "10")
    monkeypatch.delenv("DBFOX_TESTING", raising=False)

    db_path = tmp_path / "dbfox-meta-buffered-store.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    try:
        datasource = DataSource(
            id="ds-buffered-store",
            name="Buffered Store Test",
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
            question="Buffer through event store.",
        )
        store = event_store_module.create_agent_event_store(db)
        store.start_run(req, run_id="run-buffered-store", session_id="session-buffered-store")
        event = AgentRuntimeEvent(
            event_id="runtime_buffered_store_1",
            run_id="run-buffered-store",
            session_id="session-buffered-store",
            sequence=1,
            created_at_ms=1,
            type="agent.run.started",
            step={"question": "Buffer through event store."},
        )

        store.append_event("session-buffered-store", event)
        assert db.query(AgentRuntimeEventRecord).count() == 0

        store.flush()
        db.commit()

        assert db.query(AgentRun).filter(AgentRun.id == "run-buffered-store").count() == 1
        assert db.query(AgentRuntimeEventRecord).filter(AgentRuntimeEventRecord.id == event.event_id).count() == 1
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
        store = event_store_module.SQLiteAgentEventStore(db)
        store.start_run(req, run_id="run-response-artifacts", session_id="session-response-artifacts")

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
                        "depends_on": ["result_view_from_response"],
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
        assert detail["artifacts"][0]["depends_on"] == ["result_view_from_response"]
    finally:
        db.close()
        engine.dispose()
