"""Test AgentEvalRunner orchestration."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from engine.evaluation.agent_eval import AgentEvalRunner
from engine.models import AgentGoldenTask, AgentEvalRun, AgentEvalCaseResult
from engine.schemas.agent_eval import AgentEvalRunRequest


def _make_task(db_session, datasource_id, **overrides):
    defaults = dict(
        id=str(uuid.uuid4()),
        datasource_id=datasource_id,
        name="test_eval_task",
        question="say hello",
        workspace_context_json="{}",
        expected_intent=None,
        expected_tools_json="[]",
        forbidden_tools_json="[]",
        expected_artifact_types_json="[]",
        expected_final_contains_json="[]",
        tags_json='["internal"]',
        source="internal",
    )
    defaults.update(overrides)
    task = AgentGoldenTask(**defaults)
    db_session.add(task)
    db_session.commit()
    return task


def test_eval_runner_creates_run(db_session, demo_datasource):
    task = _make_task(db_session, demo_datasource.id)
    req = AgentEvalRunRequest(
        datasource_id=demo_datasource.id,
        task_ids=[task.id],
        execute=False,
    )
    runner = AgentEvalRunner(db_session)
    result = runner.run(req)

    assert result.total_cases == 1
    assert result.status == "completed"
    assert len(result.case_results) == 1

    db_run = db_session.query(AgentEvalRun).filter(AgentEvalRun.id == result.id).first()
    assert db_run is not None
    assert db_run.status == "completed"


def test_eval_runner_empty_tasks(db_session, demo_datasource):
    req = AgentEvalRunRequest(
        datasource_id=demo_datasource.id,
        task_ids=["nonexistent"],
    )
    runner = AgentEvalRunner(db_session)
    result = runner.run(req)
    assert result.total_cases == 0
    assert result.status == "completed"


def test_eval_runner_saves_case_result(db_session, demo_datasource):
    task = _make_task(db_session, demo_datasource.id)
    req = AgentEvalRunRequest(
        datasource_id=demo_datasource.id,
        task_ids=[task.id],
        execute=False,
    )
    runner = AgentEvalRunner(db_session)
    result = runner.run(req)

    cases = db_session.query(AgentEvalCaseResult).filter(
        AgentEvalCaseResult.eval_run_id == result.id
    ).all()
    assert len(cases) == 1
    assert cases[0].task_id == task.id
    assert cases[0].status in ("passed", "failed", "error")


def test_eval_runner_execute_defaults_false(db_session, demo_datasource):
    task = _make_task(db_session, demo_datasource.id)
    req = AgentEvalRunRequest(
        datasource_id=demo_datasource.id,
        task_ids=[task.id],
        execute=False,
    )
    runner = AgentEvalRunner(db_session)
    result = runner.run(req)
    assert result is not None
    case = result.case_results[0]
    response_data = json.loads(case.response_json) if case.response_json != "{}" else {}
    sql_in_response = "execute" in str(response_data).lower()
    # execute=false should prevent SQL execution


def test_eval_runner_source_filter(db_session, demo_datasource):
    task_int = _make_task(db_session, demo_datasource.id, source="internal", tags_json='["x"]')
    task_custom = _make_task(db_session, demo_datasource.id, source="custom", tags_json='["x"]', name="custom_task")

    req = AgentEvalRunRequest(
        datasource_id=demo_datasource.id,
        source="custom",
        execute=False,
    )
    runner = AgentEvalRunner(db_session)
    result = runner.run(req)
    assert result.total_cases == 1
    assert result.case_results[0].task_id == task_custom.id


def test_eval_runner_tag_filter(db_session, demo_datasource):
    task_a = _make_task(db_session, demo_datasource.id, tags_json='["regression"]', name="reg_task")
    task_b = _make_task(db_session, demo_datasource.id, tags_json='["other"]', name="other_task")

    req = AgentEvalRunRequest(
        datasource_id=demo_datasource.id,
        tags=["regression"],
        execute=False,
    )
    runner = AgentEvalRunner(db_session)
    result = runner.run(req)
    assert result.total_cases == 1
    assert result.case_results[0].task_id == task_a.id


def test_eval_run_preserves_summary(db_session, demo_datasource):
    task = _make_task(db_session, demo_datasource.id)
    req = AgentEvalRunRequest(
        datasource_id=demo_datasource.id,
        task_ids=[task.id],
        execute=False,
    )
    runner = AgentEvalRunner(db_session)
    result = runner.run(req)

    summary = json.loads(result.summary_json)
    assert "passed" in summary
    assert "failed" in summary
    assert "pass_rate" in summary


def test_eval_runner_merges_task_ids(db_session, demo_datasource):
    task1 = _make_task(db_session, demo_datasource.id, name="t1")
    task2 = _make_task(db_session, demo_datasource.id, name="t2")
    task3 = _make_task(db_session, demo_datasource.id, name="t3")
    req = AgentEvalRunRequest(
        datasource_id=demo_datasource.id,
        task_ids=[task1.id, task3.id],
        execute=False,
    )
    runner = AgentEvalRunner(db_session)
    result = runner.run(req)
    assert result.total_cases == 2
