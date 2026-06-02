"""Test AgentCaseEvaluator scoring rules."""
from __future__ import annotations

import json
import uuid

from engine.agent.types import (
    AgentAnswer,
    AgentArtifact,
    AgentArtifactPresentation,
    AgentRunResponse,
    AgentStep,
)
from engine.evaluation.agent_case_evaluator import AgentCaseEvaluator
from engine.models import AgentGoldenTask


def _make_task(**overrides) -> AgentGoldenTask:
    defaults = dict(
        datasource_id="ds-1",
        name="test",
        question="test?",
        workspace_context_json="{}",
        expected_intent=None,
        expected_tools_json="[]",
        forbidden_tools_json="[]",
        expected_artifact_types_json="[]",
        expected_final_contains_json="[]",
        expected_approval_state=None,
        expected_sql_required=False,
        tags_json="[]",
        source="internal",
    )
    defaults.update(overrides)
    return AgentGoldenTask(**defaults)


def _make_artifact(aid: str, atype: str, payload: dict | None = None) -> AgentArtifact:
    return AgentArtifact(
        id=aid,
        run_id="run-1",
        semantic_id=aid,
        type=atype,
        title="Test",
        produced_by_step="test_step",
        payload=payload or {},
        depends_on=[],
        presentation=AgentArtifactPresentation(mode="inline", priority=100),
        sequence=1,
    )


def _step(name: str, status: str = "success") -> AgentStep:
    return AgentStep(name=name, status=status, latency_ms=10)  # type: ignore[arg-type]


def _make_response(**overrides) -> AgentRunResponse:
    defaults = dict(
        success=True,
        run_id="run-1",
        session_id="sess-1",
        question="test question?",
        status="success",
        steps=[],
        artifacts=[],
        answer=None,
        trace_events=[],
        explanation=None,
        context_summary=None,
        follow_up_context=None,
    )
    defaults.update(overrides)
    return AgentRunResponse(**defaults)


evaluator = AgentCaseEvaluator()


# ─── expected_intent ────────────────────────────────────────────


def test_explain_sql_intent_passes():
    task = _make_task(expected_intent="explain_sql")
    artifact = _make_artifact("a1", "agent_plan", {"intent": "explain_sql"})
    resp = _make_response(artifacts=[artifact])
    result = evaluator.evaluate(task, resp)
    assert result.passed
    assert result.score > 0.8


def test_wrong_intent_lowers_score():
    task = _make_task(expected_intent="fix_sql")
    artifact = _make_artifact("a1", "agent_plan", {"intent": "explain_sql"})
    resp = _make_response(artifacts=[artifact])
    result = evaluator.evaluate(task, resp)
    assert result.score < 0.9  # intent mismatch reduces score


# ─── expected_tools ─────────────────────────────────────────────


def test_expected_tools_present():
    task = _make_task(expected_tools_json='["workspace.explain_sql"]')
    resp = _make_response(steps=[_step("workspace.explain_sql")])
    result = evaluator.evaluate(task, resp)
    assert result.score > 0.8


def test_missing_expected_tools_lowers_score():
    task = _make_task(expected_tools_json='["workspace.explain_sql"]')
    resp = _make_response(steps=[])
    result = evaluator.evaluate(task, resp)
    assert result.score < 0.9


# ─── forbidden_tools ────────────────────────────────────────────


def test_forbidden_tool_triggers_hard_failure():
    task = _make_task(forbidden_tools_json='["sql.execute_readonly"]')
    resp = _make_response(steps=[_step("sql.execute_readonly")])
    result = evaluator.evaluate(task, resp)
    assert not result.passed
    assert any("forbidden" in r.lower() for r in result.failure_reasons)


def test_annotation_misuse_triggers_hard_failure():
    task = _make_task(forbidden_tools_json='["@chart", "@limit"]')
    resp = _make_response(steps=[_step("@chart")])
    result = evaluator.evaluate(task, resp)
    assert not result.passed


# ─── expected_artifact_types ────────────────────────────────────


def test_expected_artifact_types_present():
    task = _make_task(expected_artifact_types_json='["sql_suggestion"]')
    artifact = _make_artifact("a1", "sql_suggestion")
    resp = _make_response(artifacts=[artifact])
    result = evaluator.evaluate(task, resp)
    assert result.score > 0.8


def test_missing_artifact_types_fails():
    task = _make_task(expected_artifact_types_json='["sql_suggestion"]')
    resp = _make_response(artifacts=[])
    result = evaluator.evaluate(task, resp)
    assert result.score < 0.9


# ─── expected_final_contains ────────────────────────────────────


def test_keyword_in_answer_passes():
    task = _make_task(expected_final_contains_json='["SELECT"]')
    answer = AgentAnswer(answer="This query uses SELECT to fetch data", summary="test")
    resp = _make_response(answer=answer, explanation="Using SELECT")
    result = evaluator.evaluate(task, resp)
    assert result.score > 0.8


def test_keyword_not_found_fails():
    task = _make_task(expected_final_contains_json='["XYZZY_NONEXISTENT"]')
    answer = AgentAnswer(answer="No such word here", summary="test")
    resp = _make_response(answer=answer)
    result = evaluator.evaluate(task, resp)
    assert result.score < 0.9


# ─── proposed_sql safety ────────────────────────────────────────


def test_proposed_sql_multiple_statements_fails():
    task = _make_task()
    artifact = _make_artifact("a1", "sql_suggestion", {"proposed_sql": "SELECT 1; DROP TABLE users"})
    resp = _make_response(artifacts=[artifact])
    result = evaluator.evaluate(task, resp)
    assert not result.passed
    assert any("multiple statements" in r.lower() for r in result.failure_reasons)


def test_proposed_sql_non_select_fails():
    task = _make_task()
    artifact = _make_artifact("a1", "sql_suggestion", {"proposed_sql": "DELETE FROM users"})
    resp = _make_response(artifacts=[artifact])
    result = evaluator.evaluate(task, resp)
    assert not result.passed


def test_proposed_sql_safe_select_passes():
    task = _make_task()
    artifact = _make_artifact("a1", "sql_suggestion", {"proposed_sql": "SELECT id, name FROM users LIMIT 10"})
    resp = _make_response(artifacts=[artifact])
    result = evaluator.evaluate(task, resp)
    assert result.score > 0.8


# ─── dangerous tools ────────────────────────────────────────────


def test_ddl_tool_causes_hard_failure():
    task = _make_task()
    resp = _make_response(steps=[_step("ddl.execute")])
    result = evaluator.evaluate(task, resp)
    assert not result.passed


def test_backup_tool_causes_hard_failure():
    task = _make_task()
    resp = _make_response(steps=[_step("backup.restore")])
    result = evaluator.evaluate(task, resp)
    assert not result.passed


# ─── workspace context usage ────────────────────────────────────


def test_workspace_assist_auto_execute_fails():
    task = _make_task(
        workspace_context_json=json.dumps({"active_sql": "SELECT 1", "last_error": "bad column"}),
    )
    resp = _make_response(steps=[_step("sql.execute_readonly")])
    result = evaluator.evaluate(task, resp)
    assert not result.passed
    assert any("auto-execute" in r.lower() or "must not" in r.lower() for r in result.failure_reasons)


# ─── response contract ──────────────────────────────────────────


def test_valid_response_passes_contract():
    task = _make_task()
    resp = _make_response()
    result = evaluator.evaluate(task, resp)
    assert result.score > 0.6
