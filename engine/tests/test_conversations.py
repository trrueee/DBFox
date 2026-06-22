"""Test Conversations API endpoints."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import engine.api.conversations as conversations_module
from engine.agent_core.types import AgentRunRequest, AgentRuntimeEvent
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


async def _streaming_response_text(response) -> str:
    if not hasattr(response, "body_iterator"):
        return response.text
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
    return "".join(chunks)


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


def test_create_conversation_endpoint(client):
    resp = client.post(
        "/api/v1/conversations",
        json={"datasource_id": "ds-1", "title": "New analysis", "context_tables": ["orders"]},
        headers=_hdrs(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New analysis"
    assert data["datasource_id"] == "ds-1"
    assert data["context_tables"] == ["orders"]
    assert data["messages"] == []


def test_prepare_conversation_message_creates_message_ids(client, db_session):
    create = client.post(
        "/api/v1/conversations",
        json={"datasource_id": "ds-1", "title": "Message test", "context_tables": []},
        headers=_hdrs(),
    )
    conv_id = create.json()["id"]

    resp = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "Count users", "api_key": "test-key", "model_name": "test-model"},
        headers=_hdrs(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversation_id"] == conv_id
    assert data["user_message_id"].startswith("msg-user-")
    assert data["assistant_message_id"].startswith("msg-assistant-")
    assert data["run_id"] is None


def test_stream_conversation_message_passes_context_tables_to_agent(monkeypatch, client, db_session):
    captured: dict[str, AgentRunRequest] = {}

    class FakeRuntime:
        def __init__(self, _db) -> None:
            pass

        def run_iter(self, req: AgentRunRequest):
            captured["req"] = req
            yield AgentRuntimeEvent(
                event_id="evt-context",
                run_id="run-context",
                sequence=1,
                created_at_ms=1,
                type="agent.run.started",
            )

    monkeypatch.setattr(conversations_module, "DBFoxAgentRuntime", FakeRuntime)
    session = AgentSession(
        id="conv-context",
        datasource_id="ds-1",
        title="Context test",
        context_tables_json=json.dumps(["orders", "orders", " customers ", "", 123], ensure_ascii=False),
    )
    db_session.add(session)
    db_session.commit()

    response = client.post(
        "/api/v1/conversations/conv-context/messages/stream",
        json={"content": "Count orders", "api_key": "test-key", "model_name": "test-model"},
        headers=_hdrs(),
    )
    body = asyncio.run(_streaming_response_text(response))

    assert response.status_code == 200
    assert "agent.run.started" in body
    req = captured["req"]
    assert req.workspace_context is not None
    assert req.workspace_context.datasource_id == "ds-1"
    assert req.workspace_context.selected_table_names == ["orders", "customers"]


def test_stream_conversation_message_ignores_malformed_context_tables(monkeypatch, client, db_session):
    captured: dict[str, AgentRunRequest] = {}

    class FakeRuntime:
        def __init__(self, _db) -> None:
            pass

        def run_iter(self, req: AgentRunRequest):
            captured["req"] = req
            yield AgentRuntimeEvent(
                event_id="evt-context-bad-json",
                run_id="run-context-bad-json",
                sequence=1,
                created_at_ms=1,
                type="agent.run.started",
            )

    monkeypatch.setattr(conversations_module, "DBFoxAgentRuntime", FakeRuntime)
    session = AgentSession(
        id="conv-bad-context",
        datasource_id="ds-1",
        title="Bad context",
        context_tables_json="{not-json",
    )
    db_session.add(session)
    db_session.commit()

    response = client.post(
        "/api/v1/conversations/conv-bad-context/messages/stream",
        json={"content": "Count orders", "api_key": "test-key", "model_name": "test-model"},
        headers=_hdrs(),
    )
    body = asyncio.run(_streaming_response_text(response))

    assert response.status_code == 200
    assert "agent.run.started" in body
    assert captured["req"].workspace_context is not None
    assert captured["req"].workspace_context.selected_table_names == []
