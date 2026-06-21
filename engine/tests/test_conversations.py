"""Test Conversations API endpoints."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import AgentArtifactRecord, AgentMessage, AgentRun, AgentSession


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _hdrs():
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def test_list_conversations_empty(client):
    resp = client.get("/api/v1/conversations", headers=_hdrs())
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_conversations_uses_agent_sessions(client, db_session):
    now = datetime.now(UTC)
    session = AgentSession(
        id="conv-list-1",
        datasource_id="ds-1",
        title="Orders analysis",
        context_tables_json='["orders"]',
        created_at=now,
        updated_at=now,
    )
    msg = AgentMessage(
        id="msg-list-user",
        session_id=session.id,
        role="user",
        content="List orders",
        status="completed",
        sequence=1,
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id="run-list-1",
        session_id=session.id,
        datasource_id="ds-1",
        user_message_id=msg.id,
        question="List orders",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([session, msg, run])
    db_session.commit()

    resp = client.get("/api/v1/conversations", headers=_hdrs())
    assert resp.status_code == 200
    data = resp.json()
    assert data == [
        {
            "id": "conv-list-1",
            "title": "Orders analysis",
            "datasource_id": "ds-1",
            "updated_at": data[0]["updated_at"],
            "last_message": "List orders",
            "message_count": 1,
            "run_status": "completed",
            "artifact_count": 0,
        }
    ]


def test_get_conversation_detail_returns_messages_runs_and_artifacts(client, db_session):
    now = datetime.now(UTC)
    session = AgentSession(
        id="conv-detail-1",
        datasource_id="ds-1",
        title="Revenue",
        context_tables_json='["orders"]',
        created_at=now,
        updated_at=now,
    )
    user = AgentMessage(
        id="msg-detail-user",
        session_id=session.id,
        role="user",
        content="Revenue?",
        status="completed",
        sequence=1,
        created_at=now,
        updated_at=now,
    )
    assistant = AgentMessage(
        id="msg-detail-assistant",
        session_id=session.id,
        role="assistant",
        content="Revenue is 100.",
        status="completed",
        sequence=2,
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id="run-detail-1",
        session_id=session.id,
        datasource_id="ds-1",
        user_message_id=user.id,
        assistant_message_id=assistant.id,
        question="Revenue?",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    artifact = AgentArtifactRecord(
        id="artifact-detail-sql",
        run_id=run.id,
        session_id=session.id,
        message_id=assistant.id,
        semantic_id="sql-1",
        type="sql",
        title="SQL 1",
        payload_json='{"sql": "select 100 as revenue"}',
        presentation_json='{"mode": "visible"}',
        depends_on_json="[]",
        status="completed",
        sequence=1,
        created_at=now,
    )
    db_session.add_all([session, user, assistant, run, artifact])
    db_session.commit()

    resp = client.get("/api/v1/conversations/conv-detail-1", headers=_hdrs())
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "conv-detail-1"
    assert [m["id"] for m in data["messages"]] == ["msg-detail-user", "msg-detail-assistant"]
    assert data["runs"][0]["id"] == "run-detail-1"
    assert data["artifacts"][0]["message_id"] == "msg-detail-assistant"
    assert data["artifacts"][0]["payload"]["sql"] == "select 100 as revenue"


def test_create_patch_and_delete_conversation(client, db_session):
    create = client.post(
        "/api/v1/conversations",
        json={"datasource_id": "ds-1", "title": "New revenue", "context_tables": ["orders"]},
        headers=_hdrs(),
    )
    assert create.status_code == 200
    detail = create.json()
    assert detail["title"] == "New revenue"
    assert detail["datasource_id"] == "ds-1"
    assert detail["context_tables"] == ["orders"]

    patch = client.patch(
        f"/api/v1/conversations/{detail['id']}",
        json={"title": "Updated revenue", "context_tables": ["orders", "customers"]},
        headers=_hdrs(),
    )
    assert patch.status_code == 200
    updated = patch.json()
    assert updated["title"] == "Updated revenue"
    assert updated["context_tables"] == ["orders", "customers"]

    delete = client.delete(f"/api/v1/conversations/{detail['id']}", headers=_hdrs())
    assert delete.status_code == 200
    assert delete.json() == {"status": "ok"}

    missing = client.get(f"/api/v1/conversations/{detail['id']}", headers=_hdrs())
    assert missing.status_code == 404
