"""Test Agent Eval SQLAlchemy models: table creation, CRUD, constraints."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from engine.db import Base
from engine.models import AgentGoldenTask, AgentEvalRun, AgentEvalCaseResult


def test_create_agent_golden_task(db_session, test_datasource):
    task = AgentGoldenTask(
        datasource_id=test_datasource.id,
        name="explain_current_sql",
        question="解释一下当前 SQL",
        workspace_context_json=json.dumps({"active_sql": "SELECT 1"}),
        expected_intent="explain_sql",
        expected_tools_json=json.dumps(["workspace.explain_sql"]),
        forbidden_tools_json=json.dumps(["sql.execute_readonly", "@limit"]),
        expected_artifact_types_json=json.dumps(["insight"]),
        expected_final_contains_json=json.dumps(["SELECT"]),
        tags_json=json.dumps(["internal", "explain"]),
        source="internal",
        difficulty="easy",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None
    assert task.datasource_id == test_datasource.id
    assert task.name == "explain_current_sql"
    assert task.source == "internal"
    assert json.loads(str(task.expected_tools_json)) == ["workspace.explain_sql"]
    assert json.loads(str(task.forbidden_tools_json)) == ["sql.execute_readonly", "@limit"]


def test_golden_task_defaults(db_session, test_datasource):
    task = AgentGoldenTask(
        datasource_id=test_datasource.id,
        name="minimal",
        question="what?",
    )
    db_session.add(task)
    db_session.commit()
    assert task.workspace_context_json == "{}"
    assert task.expected_tools_json == "[]"
    assert task.forbidden_tools_json == "[]"
    assert task.expected_artifact_types_json == "[]"
    assert task.expected_sql_required is False
    assert task.source == "internal"


def test_agent_eval_run_lifecycle(db_session, test_datasource):
    run = AgentEvalRun(
        datasource_id=test_datasource.id,
        status="running",
        total_cases=3,
        passed_cases=0,
        failed_cases=0,
        created_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert run.id is not None
    assert run.status == "running"
    assert run.total_cases == 3
    assert run.passed_cases == 0

    run.status = "completed"
    run.passed_cases = 2
    run.failed_cases = 1
    run.pass_rate = 0.6667
    run.avg_latency_ms = 1234.5
    run.completed_at = datetime.now(UTC)
    run.summary_json = json.dumps({"passed": 2, "failed": 1})
    db_session.commit()
    db_session.refresh(run)

    assert run.status == "completed"
    assert run.pass_rate == 0.6667
    assert run.avg_latency_ms == 1234.5


def test_agent_eval_case_result(db_session, test_datasource):
    task = AgentGoldenTask(
        datasource_id=test_datasource.id,
        name="test_task",
        question="test?",
    )
    db_session.add(task)
    db_session.commit()

    run = AgentEvalRun(
        datasource_id=test_datasource.id,
        total_cases=1,
        created_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()

    case = AgentEvalCaseResult(
        eval_run_id=run.id,
        task_id=task.id,
        run_id="agent-run-001",
        status="passed",
        score=0.95,
        latency_ms=500,
        actual_intent="explain_sql",
        actual_tools_json=json.dumps(["workspace.explain_sql"]),
        actual_artifact_types_json=json.dumps(["insight"]),
        failure_reasons_json="[]",
        response_json=json.dumps({"success": True}),
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    assert case.id is not None
    assert case.eval_run_id == run.id
    assert case.task_id == task.id
    assert case.status == "passed"
    assert case.score == 0.95
    assert json.loads(str(case.actual_tools_json)) == ["workspace.explain_sql"]


def test_case_result_cascade_delete(db_session, test_datasource):
    task = AgentGoldenTask(
        datasource_id=test_datasource.id,
        name="cascade_test",
        question="q",
    )
    db_session.add(task)
    db_session.commit()

    run = AgentEvalRun(
        datasource_id=test_datasource.id,
        total_cases=1,
        created_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()

    case = AgentEvalCaseResult(
        eval_run_id=run.id,
        task_id=task.id,
        status="pending",
        score=0.0,
    )
    db_session.add(case)
    db_session.commit()

    assert db_session.query(AgentEvalCaseResult).count() == 1
    db_session.delete(run)
    db_session.commit()
    assert db_session.query(AgentEvalCaseResult).count() == 0


def test_agent_eval_models_in_metadata():
    """Verify Base.metadata includes the new eval tables."""
    table_names = [t for t in Base.metadata.tables]
    assert "agent_golden_tasks" in table_names
    assert "agent_eval_runs" in table_names
    assert "agent_eval_case_results" in table_names


def test_indexes_exist():
    t = Base.metadata.tables["agent_golden_tasks"]
    index_names = {idx.name for idx in t.indexes}
    assert "ix_agent_golden_tasks_datasource" in index_names
    assert "ix_agent_golden_tasks_project" in index_names
    assert "ix_agent_golden_tasks_intent" in index_names
    assert "ix_agent_golden_tasks_source" in index_names
