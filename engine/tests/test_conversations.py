"""Public conversation API uses the canonical Session Core projections."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from engine.agent.events import RuntimeEventType
from engine.agent.resource_refs import load_resource_refs
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.run_item import dump_run_item, function_call_item
from engine.agent.session import DeliveryMode
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import (
    AgentRun,
    AgentSession,
    AgentSessionInput,
    AgentToolInvocation,
    DataSource,
    Project,
)


@pytest.fixture(autouse=True)
def conversation_datasource(db_session):
    db_session.add(Project(id="proj-test", name="Test Project"))
    db_session.add(DataSource(
        id="ds-1", name="Conversation datasource", db_type="sqlite",
        host="", port=0, database_name=":memory:", username="",
        project_id="proj-test",
    ))
    db_session.commit()


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def test_create_patch_list_and_delete_conversation(client, db_session):
    created = client.post(
        "/api/v1/conversations",
        json={
            "project_id": "proj-test",
            "title": "Revenue",
            "resource_intents": [{"kind": "dbfox.data.database", "id": "ds-1"}],
        },
        headers=_headers(),
    )
    assert created.status_code == 200
    conversation_id = created.json()["session"]["id"]
    assert created.json()["session"]["resource_intents"] == [
        {"kind": "dbfox.data.database", "id": "ds-1"}
    ]
    stored_session = db_session.get(AgentSession, conversation_id)
    assert stored_session is not None
    assert not hasattr(stored_session, "datasource_id")

    listed = client.get("/api/v1/conversations", headers=_headers())
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == conversation_id

    patched = client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Updated revenue"},
        headers=_headers(),
    )
    assert patched.json()["session"]["title"] == "Updated revenue"

    assert client.delete(f"/api/v1/conversations/{conversation_id}", headers=_headers()).json() == {"status": "ok"}
    assert client.get(f"/api/v1/conversations/{conversation_id}", headers=_headers()).status_code == 404


def test_snapshot_restores_messages_run_artifact_and_event_cursor(client, db_session):
    now = datetime.now(UTC)
    db_session.add(AgentSession(
        id="conversation-1", title="Orders", created_at=now, updated_at=now,
    ))
    db_session.flush()
    admitted = SessionRepository(db_session).admit(
        session_id="conversation-1", resource_refs=(ResourceScopeRef(kind="dbfox.data.database", id="ds-1", version=1),),
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
        declared_version="1",
        contract_hash="sha256:1",
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
    repository.events.append(
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

def test_removed_datasource_create_field_is_rejected(client):
    response = client.post(
        "/api/v1/conversations",
        json={"project_id": "proj-test", "datasource_id": "missing", "title": "Missing"},
        headers=_headers(),
    )
    assert response.status_code == 422


def test_conversation_resource_intent_is_durable_and_message_attachments_are_additive(
    client,
    db_session,
    monkeypatch,
):
    db_session.add(DataSource(
        id="ds-2", name="Analytics", db_type="sqlite",
        host="", port=0, database_name=":memory:", username="",
        project_id="proj-test",
    ))
    db_session.commit()
    created = client.post(
        "/api/v1/conversations",
        json={
            "project_id": "proj-test",
            "title": "Multi resource",
            "resource_intents": [{"kind": "dbfox.data.database", "id": "ds-1"}],
        },
        headers=_headers(),
    )
    assert created.status_code == 200
    conversation_id = created.json()["session"]["id"]
    assert created.json()["session"]["resource_intents"] == [
        {"kind": "dbfox.data.database", "id": "ds-1"}
    ]

    class Coordinator:
        available = True

        def wake(self, _session_id: str) -> None:
            return None

    monkeypatch.setattr(app.state, "agent_coordinator", Coordinator(), raising=False)
    admitted = client.post(
        f"/api/v1/conversations/{conversation_id}/inputs",
        json={
            "content": "对比两个数据库",
            "idempotency_key": "resource-intent-additive-1",
            "delivery_mode": "queue",
            "requested_resources": [{"kind": "dbfox.data.database", "id": "ds-2"}],
            "llm_credential_id": "credential-1",
        },
        headers=_headers(),
    )
    assert admitted.status_code == 202
    stored_input = db_session.get(AgentSessionInput, admitted.json()["input_id"])
    assert stored_input is not None
    refs = load_resource_refs(str(stored_input.resource_refs_json))
    assert refs is not None
    assert [ref.canonical() for ref in refs] == [
        ("dbfox.data.database", "ds-1"),
        ("dbfox.data.database", "ds-2"),
    ]
    stored_run = db_session.get(AgentRun, admitted.json()["run_id"])
    assert stored_run is not None
    assert not hasattr(stored_run, "datasource_id")
    assert not hasattr(stored_run, "datasource_generation")


def test_empty_conversation_intent_does_not_inherit_project_workspace(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    project = db_session.get(Project, "proj-test")
    assert project is not None
    db_session.commit()
    created = client.post(
        "/api/v1/conversations",
        json={"project_id": "proj-test", "title": "No implicit authority"},
        headers=_headers(),
    )
    conversation_id = created.json()["session"]["id"]

    class Coordinator:
        available = True

        def wake(self, _session_id: str) -> None:
            return None

    monkeypatch.setattr(app.state, "agent_coordinator", Coordinator(), raising=False)
    admitted = client.post(
        f"/api/v1/conversations/{conversation_id}/inputs",
        json={
            "content": "只做通用分析",
            "idempotency_key": "resource-intent-empty-1",
            "delivery_mode": "queue",
            "llm_credential_id": "credential-1",
        },
        headers=_headers(),
    )
    assert admitted.status_code == 202
    stored_input = db_session.get(AgentSessionInput, admitted.json()["input_id"])
    assert stored_input is not None
    assert load_resource_refs(str(stored_input.resource_refs_json)) == ()


def test_admission_returns_authoritative_projection_for_immediate_ui(client, monkeypatch):
    created = client.post(
        "/api/v1/conversations",
        json={"project_id": "proj-test", "title": "Streaming"},
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


def test_request_contract_rejects_missing_llm_credential_before_creating_a_run(
    client,
    db_session,
    monkeypatch,
):
    created = client.post(
        "/api/v1/conversations",
        json={"project_id": "proj-test", "title": "No credential"},
        headers=_headers(),
    )
    conversation_id = created.json()["session"]["id"]

    class Coordinator:
        available = True

        def wake(self, _session_id: str) -> None:
            raise AssertionError("Rejected input must not wake the worker")

    monkeypatch.setattr(app.state, "agent_coordinator", Coordinator(), raising=False)
    before = db_session.query(AgentRun).count()
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/inputs",
        json={
            "content": "分析订单",
            "idempotency_key": "missing-credential-input",
            "delivery_mode": "queue",
            "selected_artifact_ids": [],
            "workspace_context": {},
            "llm_credential_id": "",
            "api_base": "https://api.openai.com/v1",
            "model_name": "gpt-4.1-mini",
        },
        headers=_headers(),
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["detail"] == "Request validation failed."
    assert db_session.query(AgentRun).count() == before


def test_admission_returns_cataloged_endpoint_policy_error_without_creating_a_run(
    client,
    db_session,
):
    created = client.post(
        "/api/v1/conversations",
        json={"project_id": "proj-test", "title": "Unsafe endpoint"},
        headers=_headers(),
    )
    conversation_id = created.json()["session"]["id"]
    before = db_session.query(AgentRun).count()

    response = client.post(
        f"/api/v1/conversations/{conversation_id}/inputs",
        json={
            "content": "分析订单",
            "idempotency_key": "unsafe-endpoint-input",
            "delivery_mode": "queue",
            "selected_artifact_ids": [],
            "workspace_context": {},
            "llm_credential_id": "credential-reference",
            "api_base": "http://public.example/v1",
            "model_name": "gpt-4.1-mini",
        },
        headers=_headers(),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "LLM_ENDPOINT_NOT_ALLOWED"
    assert response.json()["detail"] == "不允许连接该模型服务地址，请检查端点配置。"
    assert db_session.query(AgentRun).count() == before


def test_snapshot_pages_messages_and_exposes_history_cursor(client, db_session):
    now = datetime.now(UTC)
    db_session.add(AgentSession(
        id="conversation-paged",
        title="Paged",
        created_at=now,
        updated_at=now,
    ))
    db_session.flush()
    repository = SessionRepository(db_session)
    for sequence in (1, 2, 3):
        repository.admit(
            session_id="conversation-paged",
            resource_refs=(ResourceScopeRef(kind="dbfox.data.database", id="ds-1", version=1),),
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
        title="Active",
        created_at=now,
        updated_at=now,
    ))
    db_session.flush()
    admitted = SessionRepository(db_session).admit(
        session_id="conversation-delete-active",
        resource_refs=(ResourceScopeRef(kind="dbfox.data.database", id="ds-1", version=1),),
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
