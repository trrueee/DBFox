"""Test Conversations API endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from engine.db import get_db
from engine.main import app, LOCAL_SECURE_TOKEN
from engine.models import ChatConversation


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


def test_save_and_list_conversations(client, db_session):
    # Create / Save conversation
    payload = {
        "id": "conv-1",
        "title": "Test Conversation 1",
        "created_at": 1700000000,
        "updated_at": 1700000010,
        "context_tables_json": '["users"]',
        "messages_json": "[]",
        "artifacts_json": "[]",
    }
    resp = client.put("/api/v1/conversations/conv-1", json=payload, headers=_hdrs())
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # List conversations
    resp = client.get("/api/v1/conversations", headers=_hdrs())
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "conv-1"
    assert data[0]["title"] == "Test Conversation 1"
    assert data[0]["context_tables_json"] == '["users"]'

    # Save update (mismatch id check)
    payload["id"] = "conv-2"
    resp = client.put("/api/v1/conversations/conv-1", json=payload, headers=_hdrs())
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CONVERSATION_ID_MISMATCH"


def test_delete_conversation(client, db_session):
    # Seed a conversation
    conv = ChatConversation(
        id="conv-to-delete",
        title="To Delete",
        created_at=1700000000,
        updated_at=1700000000,
    )
    db_session.add(conv)
    db_session.commit()

    # Delete it
    resp = client.delete("/api/v1/conversations/conv-to-delete", headers=_hdrs())
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # Verify deleted
    resp = client.get("/api/v1/conversations", headers=_hdrs())
    assert resp.status_code == 200
    assert resp.json() == []
