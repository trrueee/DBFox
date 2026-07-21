"""Public conversation API uses the canonical Session Core projections."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.session import DeliveryMode
from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import AgentSession, DataSource


@pytest.fixture
def client(db_session):
    db_session.add(DataSource(
        id="ds-1", name="Conversation datasource", db_type="sqlite",
        host="", port=0, database_name=":memory:", username="",
    ))
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    value = TestClient(app)
    yield value
    value.close()
    app.dependency_overrides.clear()


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def test_create_patch_list_and_delete_conversation(client):
    created = client.post(
        "/api/v1/conversations",
        json={"datasource_id": "ds-1", "title": "Revenue", "context_tables": ["orders"]},
        headers=_headers(),
    )
    assert created.status_code == 200
    conversation_id = created.json()["session"]["id"]
    assert created.json()["session"]["context_tables"] == ["orders"]

    listed = client.get("/api/v1/conversations", headers=_headers())
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == conversation_id

    patched = client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Updated revenue", "context_tables": ["orders", "customers"]},
        headers=_headers(),
    )
    assert patched.json()["session"]["title"] == "Updated revenue"
    assert patched.json()["session"]["context_tables"] == ["orders", "customers"]

    assert client.delete(f"/api/v1/conversations/{conversation_id}", headers=_headers()).json() == {"status": "ok"}
    assert client.get(f"/api/v1/conversations/{conversation_id}", headers=_headers()).status_code == 404


def test_snapshot_restores_messages_run_artifact_and_event_cursor(client, db_session):
    now = datetime.now(UTC)
    db_session.add(AgentSession(
        id="conversation-1", datasource_id="ds-1", title="Orders",
        context_tables_json='["orders"]', created_at=now, updated_at=now,
    ))
    db_session.flush()
    admitted = SessionRepository(db_session).admit(
        session_id="conversation-1", datasource_id="ds-1", datasource_generation=1,
        content="分析订单", idempotency_key="request-0001", llm_credential_id="credential-1",
        api_base="https://api.openai.com/v1", model_name="gpt-4.1-mini",
        request_payload={"content": "分析订单"}, delivery_mode=DeliveryMode.QUEUE,
    )
    repository = SessionRepository(db_session)
    lease = repository.claim(session_id="conversation-1", owner="api-test")
    assert lease is not None
    assert repository.promote_next_input(lease=lease) == admitted.run_id
    turn = repository.start_turn(
        lease=lease, run_id=admitted.run_id, agent_definition_version="test@1",
        prompt_version="test@1", prompt_hash="test", context_snapshot={}, context_hash="test",
        tool_materialization={"tools": []}, tool_materialization_hash="test",
        provider="test", model_name="test",
    )
    from engine.agent.artifact import ArtifactType
    ArtifactRepository(db_session).create(
        lease=lease, run_id=admitted.run_id, turn_id=turn.id,
        artifact_type=ArtifactType.SQL, title="执行的 SQL",
        payload={"sql": "SELECT * FROM orders"}, semantic_key="orders-sql",
    )
    db_session.commit()

    response = client.get("/api/v1/conversations/conversation-1", headers=_headers())
    assert response.status_code == 200
    snapshot = response.json()
    assert [item["role"] for item in snapshot["messages"]] == ["user", "assistant"]
    assert snapshot["runs"][0]["id"] == admitted.run_id
    assert snapshot["artifacts"][0]["payload"]["sql"] == "SELECT * FROM orders"
    assert "preview" not in snapshot["artifacts"][0]
    assert snapshot["cursor"] >= 1

    events = client.get("/api/v1/conversations/conversation-1/events", headers=_headers())
    assert events.status_code == 200
    assert events.json()[0]["event_type"] == "session.input.admitted"


def test_unknown_datasource_is_rejected(client):
    response = client.post(
        "/api/v1/conversations",
        json={"datasource_id": "missing", "title": "Missing"},
        headers=_headers(),
    )
    assert response.status_code == 404
