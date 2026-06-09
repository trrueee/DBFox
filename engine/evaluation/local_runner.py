"""Local Agent Eval Runner — runs eval cases against the agent and scores them.

Uses deterministic evaluators (no LLM-as-judge).  Designed to run in CI
or locally without external services.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from engine.evaluation.schemas import AgentEvalCase, AgentEvalCaseResult
from engine.evaluation.evaluators.planner_eval import evaluate_planner
from engine.evaluation.evaluators.trajectory_eval import evaluate_trajectory
from engine.evaluation.evaluators.policy_eval import evaluate_policy
from engine.evaluation.evaluators.sql_eval import evaluate_sql
from engine.evaluation.evaluators.artifact_eval import evaluate_artifacts
from engine.evaluation.evaluators.answer_eval import evaluate_answer

logger = logging.getLogger("databox.eval.local_runner")


class LocalEvalRunner:
    """Run eval cases locally and produce structured results.

    Does NOT require a live LLM — cases can be scored against pre-recorded
    traces, or the runner can invoke the agent directly if a db session is
    provided.
    """

    def evaluate_case(
        self,
        case: AgentEvalCase,
        *,
        plan_directive: dict[str, Any] | None = None,
        tools_called: list[str] | None = None,
        blocked_tools: list[str] | None = None,
        approval_tools: list[str] | None = None,
        sql_executed: bool = False,
        sql_text: str | None = None,
        safety: dict | None = None,
        artifact_types: list[str] | None = None,
        artifact_count: int = 0,
        answer_text: str | None = None,
    ) -> AgentEvalCaseResult:
        """Evaluate a case with pre-collected trace data.

        This method accepts trace data directly so it can be used with
        recorded traces (no live agent needed).
        """
        failures: list[str] = []
        expected = case.expected
        tools = tools_called or []
        blocked = blocked_tools or []
        approval = approval_tools or []
        arts = artifact_types or []

        # Planner
        if expected.planner:
            failures.extend(evaluate_planner(plan_directive, expected.planner))

        # Trajectory
        if expected.trajectory:
            failures.extend(evaluate_trajectory(tools, expected.trajectory))

        # Policy
        if expected.policy:
            failures.extend(evaluate_policy(blocked, approval, sql_executed, expected.policy))

        # SQL
        if expected.sql:
            failures.extend(evaluate_sql(sql_text, safety, tools, expected.sql))

        # Artifacts
        if expected.artifacts:
            failures.extend(evaluate_artifacts(arts, artifact_count, expected.artifacts))

        # Answer
        if expected.answer:
            failures.extend(evaluate_answer(answer_text, tools, expected.answer))

        passed = len(failures) == 0

        return AgentEvalCaseResult(
            case_id=case.id,
            passed=passed,
            failures=failures,
            actual_plan_directive=plan_directive,
            actual_tools_called=tools,
            actual_artifacts=arts,
            actual_answer=answer_text,
        )

    def run_cases(
        self,
        cases: list[AgentEvalCase],
        **trace_data: Any,
    ) -> list[AgentEvalCaseResult]:
        """Run multiple cases with shared trace data.  Returns results."""
        results: list[AgentEvalCaseResult] = []
        for case in cases:
            result = self.evaluate_case(case, **trace_data)
            results.append(result)
        return results

    @staticmethod
    def load_cases(path: str | Path) -> list[AgentEvalCase]:
        """Load eval cases from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [AgentEvalCase.model_validate(item) for item in data]
        if isinstance(data, dict) and "cases" in data:
            return [AgentEvalCase.model_validate(item) for item in data["cases"]]
        raise ValueError(f"Unexpected eval cases format in {path}")

    @staticmethod
    def print_report(results: list[AgentEvalCaseResult]) -> str:
        """Print a human-readable report and return it as a string."""
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        lines = [
            f"Eval Report: {passed}/{total} passed",
            "=" * 50,
        ]
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"[{status}] {r.case_id}")
            if r.failures:
                for f in r.failures:
                    lines.append(f"  - {f}")
        lines.append("=" * 50)
        lines.append(f"Pass rate: {passed}/{total} ({100*passed//total if total else 0}%)")
        report = "\n".join(lines)
        print(report)
        return report
