"""Public conversation API uses the canonical Session Core projections."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from engine.agent.events import RuntimeEventType
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.run_item import dump_run_item, function_call_item
from engine.agent.session import DeliveryMode
from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import (
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentToolInvocation,
    DataSource,
)


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
    invocation = AgentToolInvocation(
        id="invocation-trace",
        session_id="conversation-1",
        run_id=admitted.run_id,
        turn_id=str(turn.id),
        provider_call_id="provider-call-trace",
        tool_name="db_observe",
        tool_version="1",
        input_json="{}",
        input_hash="input-hash-trace",
        idempotency_key="idempotency-trace",
        status="succeeded",
        policy_json='{"status":"allowed","risk_level":"safe"}',
        presentation_json=(
            '{"title":"读取数据库概览","category":"explore",'
            '"visibility":"summary","progress":"indeterminate"}'
        ),
        recovery_policy="retry_safe",
        attempt_count=1,
    )
    db_session.add(invocation)
    db_session.flush()
    repository.append_event(
        lease=lease,
        event_type=RuntimeEventType.RUN_ITEM_COMPLETED,
        run_id=admitted.run_id,
        turn_id=str(turn.id),
        payload={"item": dump_run_item(function_call_item(invocation))},
    )
    from engine.agent.artifact import ArtifactType
    ArtifactRepository(db_session).create(
        lease=lease, run_id=admitted.run_id, turn_id=turn.id,
        artifact_type=ArtifactType.SQL, title="执行的 SQL",
        payload={
            "sql": "SELECT * FROM orders",
            "safeSql": "SELECT * FROM orders",
            "dialect": "sqlite",
            "queryFingerprint": "orders-query",
        },
        semantic_key="orders-sql",
    )
    db_session.commit()

    response = client.get("/api/v1/conversations/conversation-1", headers=_headers())
    assert response.status_code == 200
    snapshot = response.json()
    assert [item["type"] for item in snapshot["items"]] == ["message", "function_call"]
    assert snapshot["runs"][0]["id"] == admitted.run_id
    assert "artifacts" not in snapshot
    assert snapshot["cursor"] >= 1

    events = client.get("/api/v1/conversations/conversation-1/events", headers=_headers())
    assert events.status_code == 200
    assert events.json()[0]["event_type"] == "run.started"

    artifacts = client.get(
        f"/api/v1/conversations/conversation-1/runs/{admitted.run_id}/artifacts",
        headers=_headers(),
    )
    assert artifacts.status_code == 200
    assert artifacts.json()[0]["type"] == "sql"

def test_unknown_datasource_is_rejected(client):
    response = client.post(
        "/api/v1/conversations",
        json={"datasource_id": "missing", "title": "Missing"},
        headers=_headers(),
    )
    assert response.status_code == 404


def test_admission_returns_authoritative_projection_for_immediate_ui(client, monkeypatch):
    created = client.post(
        "/api/v1/conversations",
        json={"datasource_id": "ds-1", "title": "Streaming", "context_tables": ["orders"]},
        headers=_headers(),
    )
    conversation_id = created.json()["session"]["id"]

    class Coordinator:
        available = True

        def wake(self, _session_id: str) -> None:
            return None

    monkeypatch.setattr(app.state, "agent_coordinator", Coordinator(), raising=False)
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/inputs",
        json={
            "content": "分析最近订单",
            "idempotency_key": "request-streaming-0001",
            "delivery_mode": "queue",
            "selected_artifact_ids": [],
            "workspace_context": {"selected_table_names": ["orders"]},
            "llm_credential_id": "credential-1",
            "api_base": "https://api.openai.com/v1",
            "model_name": "gpt-4.1-mini",
        },
        headers=_headers(),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["event_cursor"] == body["projection"]["cursor"]
    assert body["projection"]["protocol_version"] == 2
    assert [item["type"] for item in body["projection"]["items"]] == ["message"]
    assert body["projection"]["items"][0]["payload"]["content"] == "分析最近订单"
    projected_run = body["projection"]["runs"][0]
    assert projected_run["id"] == body["run_id"]
    assert projected_run["question"] == "分析最近订单"
    assert projected_run["status"] == "queued"
    assert projected_run["user_message_id"] == body["user_message_id"]
    assert "assistant_message_id" not in body


def test_snapshot_pages_messages_and_exposes_history_cursor(client, db_session):
    now = datetime.now(UTC)
    db_session.add(AgentSession(
        id="conversation-paged",
        datasource_id="ds-1",
        title="Paged",
        created_at=now,
        updated_at=now,
    ))
    db_session.flush()
    repository = SessionRepository(db_session)
    for sequence in (1, 2, 3):
        repository.admit(
            session_id="conversation-paged",
            datasource_id="ds-1",
            datasource_generation=1,
            content=f"message {sequence}",
            idempotency_key=f"paged-{sequence}",
            llm_credential_id="credential-1",
            api_base=None,
            model_name="model",
            request_payload={},
        )
    db_session.commit()

    latest = client.get(
        "/api/v1/conversations/conversation-paged?item_limit=2",
        headers=_headers(),
    ).json()
    assert [item["sequence"] for item in latest["items"]] == [4, 6]
    assert latest["pagination"]["items"] == {
        "has_more": True,
        "next_before_sequence": 4,
    }

    history = client.get(
        "/api/v1/conversations/conversation-paged/history"
        "?before_item_sequence=4&item_limit=2",
        headers=_headers(),
    ).json()
    assert [item["sequence"] for item in history["items"]] == [2]


def test_delete_active_conversation_soft_deletes_and_requests_cancel(
    client, db_session, monkeypatch
):
    now = datetime.now(UTC)
    db_session.add(AgentSession(
        id="conversation-delete-active",
        datasource_id="ds-1",
        title="Active",
        created_at=now,
        updated_at=now,
    ))
    db_session.flush()
    admitted = SessionRepository(db_session).admit(
        session_id="conversation-delete-active",
        datasource_id="ds-1",
        datasource_generation=1,
        content="分析订单",
        idempotency_key="delete-active",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    db_session.commit()

    class RecordingCoordinator:
        def __init__(self):
            self.woken = []
            self.available = True

        def wake(self, session_id):
            self.woken.append(session_id)

    coordinator = RecordingCoordinator()
    monkeypatch.setattr(app.state, "agent_coordinator", coordinator, raising=False)

    response = client.delete(
        "/api/v1/conversations/conversation-delete-active",
        headers=_headers(),
    )

    assert response.json() == {"status": "deleting"}
    assert client.get(
        "/api/v1/conversations/conversation-delete-active",
        headers=_headers(),
    ).status_code == 404
    aggregate = db_session.get(AgentSession, "conversation-delete-active")
    run = db_session.get(AgentRun, admitted.run_id)
    assert aggregate is not None and aggregate.deleted_at is not None
    assert run is not None and run.status == "cancelling"
    assert coordinator.woken == ["conversation-delete-active"]
