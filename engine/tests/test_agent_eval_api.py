from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import AgentGoldenTask


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    value = TestClient(app)
    yield value
    value.close()
    app.dependency_overrides.clear()


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def test_golden_task_crud(client, test_datasource):
    payload = {
        "datasource_id": test_datasource.id, "name": "orders", "question": "分析订单",
        "workspace_context_json": "{}", "expected_intent": None,
        "expected_tools_json": '["sql.validate"]', "forbidden_tools_json": "[]",
        "expected_artifact_types_json": '["sql"]', "expected_final_contains_json": "[]",
        "tags_json": '["internal"]', "source": "internal", "difficulty": "easy",
    }
    created = client.post("/api/v1/agent-eval/tasks", json=payload, headers=_headers())
    assert created.status_code == 200
    task_id = created.json()["id"]
    assert json.loads(created.json()["expected_tools_json"]) == ["sql.validate"]

    listed = client.get(
        f"/api/v1/agent-eval/tasks?datasource_id={test_datasource.id}", headers=_headers(),
    )
    assert [item["id"] for item in listed.json()] == [task_id]

    updated = client.put(
        f"/api/v1/agent-eval/tasks/{task_id}", json={"name": "orders-v2"}, headers=_headers(),
    )
    assert updated.json()["name"] == "orders-v2"
    assert client.delete(f"/api/v1/agent-eval/tasks/{task_id}", headers=_headers()).json()["success"] is True


def test_run_endpoint_requires_a_model_credential(client, db_session, test_datasource):
    task = AgentGoldenTask(datasource_id=test_datasource.id, name="orders", question="分析订单")
    db_session.add(task)
    db_session.commit()
    response = client.post(
        "/api/v1/agent-eval/run",
        json={"datasource_id": test_datasource.id, "task_ids": [task.id]},
        headers=_headers(),
    )
    assert response.status_code == 422


def test_unknown_run_returns_not_found(client):
    response = client.get("/api/v1/agent-eval/runs/missing", headers=_headers())
    assert response.status_code == 404
