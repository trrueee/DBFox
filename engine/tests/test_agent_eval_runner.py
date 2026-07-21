from __future__ import annotations

import json
import uuid

from engine.agent.service import AgentExecutionAnswer, AgentExecutionArtifact, AgentExecutionResult
from engine.evaluation.agent_case_evaluator import _extract_approval_state
from engine.evaluation.agent_eval import AgentEvalRunner
from engine.models import AgentEvalCaseResult, AgentEvalRun, AgentGoldenTask
from engine.schemas.agent_eval import AgentEvalRunRequest


def _task(db, datasource_id: str, **overrides):
    values = dict(
        id=str(uuid.uuid4()), datasource_id=datasource_id, name="orders",
        question="分析订单", workspace_context_json='{"selected_table_names":["orders"]}',
        expected_tools_json='["sql.validate"]', forbidden_tools_json="[]",
        expected_artifact_types_json='["sql"]', expected_final_contains_json='["100"]',
        tags_json='["internal"]', source="internal",
    )
    values.update(overrides)
    row = AgentGoldenTask(**values)
    db.add(row)
    db.commit()
    return row


def _completed_result() -> tuple[AgentExecutionResult, list[dict[str, object]]]:
    result = AgentExecutionResult(
        run_id="run-eval", session_id="session-eval", status="completed", success=True,
        question="分析订单", sql="SELECT 100", explanation="订单金额是 100",
        answer=AgentExecutionAnswer(answer="订单金额是 100"),
        artifacts=[AgentExecutionArtifact(
            id="artifact-sql", type="sql", title="SQL", payload={"safe_sql": "SELECT 100"},
        )],
    )
    events = [{
        "event_type": "tool.completed",
        "payload": {"tool_invocation": {"id": "inv-1", "tool_name": "sql.validate", "status": "succeeded"}},
    }]
    return result, events


def test_eval_runner_persists_result_from_the_canonical_execution_service(db_session, test_datasource, monkeypatch):
    task = _task(db_session, test_datasource.id)
    monkeypatch.setattr("engine.evaluation.agent_eval.execute_agent_sync", lambda _request: _completed_result())

    response = AgentEvalRunner(db_session).run(AgentEvalRunRequest(
        datasource_id=test_datasource.id, task_ids=[task.id],
        llm_credential_id="credential-eval", execute=False,
    ))

    assert response.status == "completed"
    assert response.passed_cases == 1
    stored_run = db_session.get(AgentEvalRun, response.id)
    assert stored_run is not None and stored_run.status == "completed"
    stored_case = db_session.query(AgentEvalCaseResult).filter_by(eval_run_id=response.id).one()
    assert json.loads(stored_case.actual_sql_json) == ["SELECT 100"]
    assert json.loads(stored_case.actual_tools_json) == ["sql.validate"]


def test_eval_runner_handles_an_empty_task_selection(db_session, test_datasource):
    response = AgentEvalRunner(db_session).run(AgentEvalRunRequest(
        datasource_id=test_datasource.id, task_ids=["missing"],
        llm_credential_id="credential-eval",
    ))
    assert response.total_cases == 0
    assert response.status == "completed"


def test_eval_runner_records_safe_failure_without_provider_text(db_session, test_datasource, monkeypatch):
    task = _task(db_session, test_datasource.id)

    def fail(_request):
        raise RuntimeError("authorization=secret-sentinel")

    monkeypatch.setattr("engine.evaluation.agent_eval.execute_agent_sync", fail)
    response = AgentEvalRunner(db_session).run(AgentEvalRunRequest(
        datasource_id=test_datasource.id, task_ids=[task.id], llm_credential_id="credential-eval",
    ))
    stored = db_session.query(AgentEvalCaseResult).filter_by(eval_run_id=response.id).one()
    assert stored.status == "error"
    assert "secret-sentinel" not in stored.response_json


def test_approval_evaluation_uses_the_latest_durable_decision():
    result, _ = _completed_result()
    events = [
        {
            "event_type": "approval.requested",
            "payload": {"approval": {"status": "pending"}},
        },
        {
            "event_type": "approval.resolved",
            "payload": {"approval": {"status": "rejected"}},
        },
    ]

    assert _extract_approval_state(result, events) == "rejected"


def test_successful_run_without_approval_is_not_reported_as_approved():
    result, _ = _completed_result()

    assert _extract_approval_state(result, []) == "none"
