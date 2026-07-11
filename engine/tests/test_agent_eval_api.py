"""Test Agent Eval API endpoints."""
from __future__ import annotations

import json
import logging

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from engine.agent_core.types import AgentRunResponse, AgentRuntimeEvent
from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.db import get_db
from engine.evaluation.agent_eval import AgentEvalRunner
from engine.main import app, LOCAL_SECURE_TOKEN
from engine.models import AgentEvalCaseResult, AgentGoldenTask, AgentEvalRun
from engine.schemas.agent_eval import AgentEvalRunRequest


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


def test_testclient_startup_keeps_dbfox_error_loggers_enabled(client) -> None:
    del client
    assert not logging.getLogger("dbfox.datasource").disabled
    assert not logging.getLogger("dbfox.environment.schema_introspector").disabled


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


def test_eval_response_sink_never_persists_or_returns_runtime_error_text(
    client,
    db_session,
    test_datasource,
    monkeypatch,
    caplog,
):
    sentinel = "agent-eval-response-sink-sentinel"
    task = AgentGoldenTask(
        datasource_id=test_datasource.id,
        name="response_sink_boundary",
        question="show orders",
        workspace_context_json="{}",
        expected_tools_json="[]",
        forbidden_tools_json="[]",
        expected_artifact_types_json="[]",
        expected_final_contains_json="[]",
        tags_json="[]",
        source="internal",
    )
    db_session.add(task)
    db_session.commit()

    class FailingResponseRuntime:
        def __init__(self, _db):
            pass

        def run_iter(self, _request):
            response = AgentRunResponse(
                run_id="eval-response-sink-run",
                session_id="eval-response-sink-session",
                success=False,
                status="failed",
                question="show orders",
                error=sentinel,
            )
            yield AgentRuntimeEvent(
                event_id="eval-response-sink-step",
                run_id=response.run_id,
                sequence=1,
                created_at_ms=1,
                type="agent.step.completed",
                step={"root_cause": sentinel, "error": sentinel},
            )
            yield AgentRuntimeEvent(
                event_id="eval-response-sink-final",
                run_id=response.run_id,
                sequence=2,
                created_at_ms=2,
                type="agent.run.failed",
                response=response,
                error=sentinel,
            )

    monkeypatch.setattr(
        "engine.evaluation.agent_eval.DBFoxAgentRuntime",
        FailingResponseRuntime,
    )
    capture_logger = logging.Logger("test.agent_eval_response_sink")
    capture_logger.setLevel(logging.ERROR)
    capture_logger.propagate = False
    capture_logger.addHandler(caplog.handler)
    try:
        monkeypatch.setattr("engine.evaluation.agent_eval.logger", capture_logger)
        result = AgentEvalRunner(db_session).run(
            AgentEvalRunRequest(
                datasource_id=test_datasource.id,
                task_ids=[task.id],
                execute=False,
            )
        )
    finally:
        capture_logger.removeHandler(caplog.handler)
    stored_case = db_session.query(AgentEvalCaseResult).filter(
        AgentEvalCaseResult.eval_run_id == result.id
    ).one()

    assert stored_case.status != "error", caplog.text
    assert sentinel not in stored_case.response_json
    assert fixed_error_message(FixedErrorCode.AGENT_RUNTIME_ERROR) in stored_case.response_json

    response = client.get(
        f"/api/v1/agent-eval/runs/{result.id}",
        headers=_hdrs(),
    )
    assert response.status_code == 200
    assert sentinel not in response.text
    assert fixed_error_message(FixedErrorCode.AGENT_RUNTIME_ERROR) in response.text


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


def test_run_eval_unexpected_failure_never_leaks_exception_text(
    db_session,
    test_datasource,
    monkeypatch,
    caplog,
):
    import engine.api.agent_eval as agent_eval_api

    sentinel = "agent-eval-api-secret-sentinel"

    class FailingRunner:
        def __init__(self, _db):
            pass

        def run(self, _request):
            raise RuntimeError(f"provider authorization={sentinel}")

    monkeypatch.setattr(agent_eval_api, "AgentEvalRunner", FailingRunner)

    capture_logger = logging.Logger("test.agent_eval_api_boundary")
    capture_logger.setLevel(logging.ERROR)
    capture_logger.propagate = False
    capture_logger.addHandler(caplog.handler)
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(agent_eval_api, "logger", capture_logger)
            with pytest.raises(HTTPException) as exc_info:
                agent_eval_api.api_run_eval(
                    agent_eval_api.AgentEvalRunRequest(
                        datasource_id=test_datasource.id,
                        execute=False,
                    ),
                    db_session,
                )
    finally:
        capture_logger.removeHandler(caplog.handler)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "EVAL_RUN_ERROR",
        "message": "The evaluation run could not be completed.",
    }
    assert sentinel not in repr(exc_info.value.detail)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "agent_eval_run" in caplog.text


def test_cannot_update_nonexistent_task(client, test_datasource):
    resp = client.put("/api/v1/agent-eval/tasks/nonexistent", json={"name": "x"}, headers=_hdrs())
    assert resp.status_code == 404


def test_cannot_delete_nonexistent_task(client, test_datasource):
    resp = client.delete("/api/v1/agent-eval/tasks/nonexistent", headers=_hdrs())
    assert resp.status_code == 404
