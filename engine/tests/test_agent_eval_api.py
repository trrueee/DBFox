"""Test Agent Eval API endpoints."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from engine.db import get_db
from engine.main import app, LOCAL_SECURE_TOKEN
from engine.models import AgentGoldenTask, AgentEvalRun


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


def test_list_tasks_empty(client, test_datasource):
    resp = client.get(
        f"/api/v1/agent-eval/tasks?datasource_id={test_datasource.id}",
        headers=_hdrs(),
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_task(client, test_datasource):
    payload = {
        "datasource_id": test_datasource.id,
        "name": "test_task",
        "question": "test question?",
        "workspace_context_json": "{}",
        "expected_intent": "explain_sql",
        "expected_tools_json": '["workspace.explain_sql"]',
        "forbidden_tools_json": '["sql.execute_readonly"]',
        "expected_artifact_types_json": '["insight"]',
        "expected_final_contains_json": "[]",
        "tags_json": '["internal"]',
        "source": "internal",
        "difficulty": "easy",
    }
    resp = client.post("/api/v1/agent-eval/tasks", json=payload, headers=_hdrs())
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test_task"
    assert data["datasource_id"] == test_datasource.id
    assert json.loads(data["expected_tools_json"]) == ["workspace.explain_sql"]


def test_update_task(client, db_session, test_datasource):
    task = AgentGoldenTask(
        datasource_id=test_datasource.id,
        name="old_name",
        question="old?",
    )
    db_session.add(task)
    db_session.commit()

    resp = client.put(
        f"/api/v1/agent-eval/tasks/{task.id}",
        json={"name": "new_name"},
        headers=_hdrs(),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new_name"


def test_delete_task(client, db_session, test_datasource):
    task = AgentGoldenTask(
        datasource_id=test_datasource.id,
        name="to_delete",
        question="q",
    )
    db_session.add(task)
    db_session.commit()

    resp = client.delete(f"/api/v1/agent-eval/tasks/{task.id}", headers=_hdrs())
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_list_tasks_filters(client, db_session, test_datasource):
    t1 = AgentGoldenTask(datasource_id=test_datasource.id, name="t1", question="q1", source="internal", tags_json='["tag_a"]')
    t2 = AgentGoldenTask(datasource_id=test_datasource.id, name="t2", question="q2", source="custom", tags_json='["tag_b"]')
    db_session.add_all([t1, t2])
    db_session.commit()

    resp = client.get(f"/api/v1/agent-eval/tasks?datasource_id={test_datasource.id}&source=custom", headers=_hdrs())
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "custom"

    resp = client.get(f"/api/v1/agent-eval/tasks?datasource_id={test_datasource.id}&tag=tag_a", headers=_hdrs())
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_run_detailed(client, db_session, test_datasource):
    run = AgentEvalRun(
        datasource_id=test_datasource.id,
        status="completed",
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        pass_rate=1.0,
    )
    db_session.add(run)
    db_session.commit()

    resp = client.get(f"/api/v1/agent-eval/runs/{run.id}", headers=_hdrs())
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["total_cases"] == 1


def test_list_runs(client, db_session, test_datasource):
    run = AgentEvalRun(datasource_id=test_datasource.id, status="completed", total_cases=2)
    db_session.add(run)
    db_session.commit()

    resp = client.get(f"/api/v1/agent-eval/runs?datasource_id={test_datasource.id}", headers=_hdrs())
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_import_benchmark_custom_payload(client, test_datasource):
    payload = {
        "datasource_id": test_datasource.id,
        "source": "custom",
        "payload": {"question": "How many users?", "db_id": "test_db", "difficulty": "easy"},
    }
    resp = client.post("/api/v1/agent-eval/import-benchmark", json=payload, headers=_hdrs())
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "custom"
    assert data["total_imported"] == 1
    assert len(data["task_ids"]) == 1


def test_cannot_update_nonexistent_task(client, test_datasource):
    resp = client.put("/api/v1/agent-eval/tasks/nonexistent", json={"name": "x"}, headers=_hdrs())
    assert resp.status_code == 404


def test_cannot_delete_nonexistent_task(client, test_datasource):
    resp = client.delete("/api/v1/agent-eval/tasks/nonexistent", headers=_hdrs())
    assert resp.status_code == 404
