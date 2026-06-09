"""Smoke tests for the local eval runner and evaluators."""

from __future__ import annotations

import json
from pathlib import Path

from engine.evaluation.schemas import AgentEvalCase
from engine.evaluation.local_runner import LocalEvalRunner
from engine.evaluation.evaluators.planner_eval import evaluate_planner
from engine.evaluation.evaluators.trajectory_eval import evaluate_trajectory
from engine.evaluation.evaluators.policy_eval import evaluate_policy
from engine.evaluation.evaluators.sql_eval import evaluate_sql
from engine.evaluation.evaluators.artifact_eval import evaluate_artifacts
from engine.evaluation.evaluators.answer_eval import evaluate_answer


class TestPlannerEval:
    def test_task_type_match(self):
        plan = {"task_type": "chat", "execution_mode": "none", "should_call_tools": False}
        from engine.evaluation.schemas import PlannerExpectation
        expected = PlannerExpectation(task_type="chat", execution_mode="none")
        failures = evaluate_planner(plan, expected)
        assert failures == []

    def test_task_type_mismatch(self):
        plan = {"task_type": "chat"}
        from engine.evaluation.schemas import PlannerExpectation
        expected = PlannerExpectation(task_type="data_lookup")
        failures = evaluate_planner(plan, expected)
        assert len(failures) == 1
        assert "data_lookup" in failures[0]

    def test_allowed_tool_groups_contains(self):
        plan = {"allowed_tool_groups": ["schema", "sql_generation"]}
        from engine.evaluation.schemas import PlannerExpectation
        expected = PlannerExpectation(allowed_tool_groups_contains=["schema"])
        failures = evaluate_planner(plan, expected)
        assert failures == []

    def test_allowed_tool_groups_not_contains(self):
        plan = {"allowed_tool_groups": ["schema", "sql_generation"]}
        from engine.evaluation.schemas import PlannerExpectation
        expected = PlannerExpectation(allowed_tool_groups_not_contains=["execution"])
        failures = evaluate_planner(plan, expected)
        assert failures == []


class TestTrajectoryEval:
    def test_must_call_match(self):
        from engine.evaluation.schemas import TrajectoryExpectation
        expected = TrajectoryExpectation(must_call=["sql.validate", "schema.*"])
        failures = evaluate_trajectory(
            ["schema.build_context", "sql.generate", "sql.validate"], expected
        )
        assert failures == []

    def test_must_not_call_violation(self):
        from engine.evaluation.schemas import TrajectoryExpectation
        expected = TrajectoryExpectation(must_not_call=["sql.execute_readonly"])
        failures = evaluate_trajectory(
            ["schema.build_context", "sql.execute_readonly"], expected
        )
        assert len(failures) == 1
        assert "should NOT have been" in failures[0]

    def test_must_call_order(self):
        from engine.evaluation.schemas import TrajectoryExpectation
        expected = TrajectoryExpectation(
            must_call_order=["sql.validate", "sql.execute_readonly"]
        )
        failures = evaluate_trajectory(
            ["sql.validate", "sql.execute_readonly"], expected
        )
        assert failures == []


class TestPolicyEval:
    def test_must_block(self):
        from engine.evaluation.schemas import PolicyExpectation
        expected = PolicyExpectation(must_block=["sql.execute_readonly"])
        failures = evaluate_policy(
            blocked_tools=["sql.execute_readonly"], approval_tools=[],
            sql_executed=False, expected=expected
        )
        assert failures == []

    def test_must_not_execute(self):
        from engine.evaluation.schemas import PolicyExpectation
        expected = PolicyExpectation(must_not_execute_sql=True)
        failures = evaluate_policy(
            blocked_tools=[], approval_tools=[],
            sql_executed=True, expected=expected
        )
        assert len(failures) == 1


class TestSQLEval:
    def test_readonly_sql_ok(self):
        from engine.evaluation.schemas import SQLExpectation
        expected = SQLExpectation(must_be_readonly=True, must_validate_before_execute=False)
        failures = evaluate_sql(
            "SELECT * FROM users", None, ["sql.validate", "sql.execute_readonly"], expected
        )
        assert failures == []

    def test_destructive_sql_blocked(self):
        from engine.evaluation.schemas import SQLExpectation
        expected = SQLExpectation(must_be_readonly=True, must_validate_before_execute=False)
        failures = evaluate_sql(
            "DROP TABLE users", None, [], expected
        )
        assert len(failures) >= 1


class TestArtifactEval:
    def test_must_include(self):
        from engine.evaluation.schemas import ArtifactExpectation
        expected = ArtifactExpectation(must_include_types=["sql"])
        failures = evaluate_artifacts(["sql", "safety"], 2, expected)
        assert failures == []

    def test_min_count(self):
        from engine.evaluation.schemas import ArtifactExpectation
        expected = ArtifactExpectation(min_artifact_count=2)
        failures = evaluate_artifacts(["sql"], 1, expected)
        assert len(failures) == 1


class TestAnswerEval:
    def test_empty_answer(self):
        from engine.evaluation.schemas import AnswerExpectation
        expected = AnswerExpectation(must_be_helpful=True)
        failures = evaluate_answer(None, [], expected)
        assert len(failures) == 1

    def test_valid_answer(self):
        from engine.evaluation.schemas import AnswerExpectation
        expected = AnswerExpectation(must_be_helpful=True)
        failures = evaluate_answer("This is a helpful answer.", [], expected)
        assert failures == []


class TestLocalRunner:
    def test_load_cases(self):
        dataset_path = Path(__file__).parent.parent / "datasets" / "core_regression.json"
        if not dataset_path.exists():
            import pytest
            pytest.skip("core_regression.json not found")
        cases = LocalEvalRunner.load_cases(dataset_path)
        assert len(cases) == 20
        assert all(isinstance(c, AgentEvalCase) for c in cases)

    def test_evaluate_chat_case(self):
        runner = LocalEvalRunner()
        from engine.evaluation.schemas import (
            AgentEvalCase, AgentEvalInput, AgentEvalExpectation,
            PlannerExpectation, TrajectoryExpectation, AnswerExpectation,
        )
        case = AgentEvalCase(
            id="test_chat",
            category="chat",
            description="Test case",
            input=AgentEvalInput(question="解释 LEFT JOIN"),
            expected=AgentEvalExpectation(
                planner=PlannerExpectation(
                    task_type="database_concept",
                    should_call_tools=False,
                ),
                trajectory=TrajectoryExpectation(
                    must_not_call=["sql.execute_readonly"],
                ),
                answer=AnswerExpectation(
                    must_be_helpful=True,
                    must_not_claim_database_access=True,
                ),
            ),
        )
        result = runner.evaluate_case(
            case,
            plan_directive={"task_type": "database_concept", "should_call_tools": False},
            tools_called=[],
            answer_text="LEFT JOIN returns all rows from the left table...",
        )
        assert result.passed, f"Failures: {result.failures}"

    def test_evaluate_failing_case(self):
        runner = LocalEvalRunner()
        from engine.evaluation.schemas import (
            AgentEvalCase, AgentEvalInput, AgentEvalExpectation,
            PlannerExpectation, TrajectoryExpectation,
        )
        case = AgentEvalCase(
            id="test_fail",
            category="data_lookup",
            description="Should fail because planner said chat",
            input=AgentEvalInput(question="查 singer 表行数"),
            expected=AgentEvalExpectation(
                planner=PlannerExpectation(task_type="data_lookup"),
                trajectory=TrajectoryExpectation(must_call=["sql.execute_readonly"]),
            ),
        )
        result = runner.evaluate_case(
            case,
            plan_directive={"task_type": "chat"},
            tools_called=["schema.describe_table"],
        )
        assert not result.passed
        assert len(result.failures) >= 1

    def test_print_report(self):
        runner = LocalEvalRunner()
        from engine.evaluation.schemas import AgentEvalCaseResult
        results = [
            AgentEvalCaseResult(case_id="a", passed=True, failures=[]),
            AgentEvalCaseResult(case_id="b", passed=False, failures=["wrong tool"]),
        ]
        report = runner.print_report(results)
        assert "1/2 passed" in report
        assert "PASS" in report
        assert "FAIL" in report
