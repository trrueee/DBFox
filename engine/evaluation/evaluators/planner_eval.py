"""Planner evaluator — checks AgentPlanDirective against expectations."""

from __future__ import annotations

from typing import Any

from engine.evaluation.schemas import PlannerExpectation


def evaluate_planner(
    plan_directive: dict[str, Any] | None,
    expected: PlannerExpectation | None,
) -> list[str]:
    """Evaluate planner output against expectations.  Returns failure reasons."""
    if expected is None:
        return []
    if plan_directive is None:
        return ["Planner produced no plan_directive."]

    failures: list[str] = []

    if expected.task_type and plan_directive.get("task_type") != expected.task_type:
        failures.append(
            f"Expected task_type={expected.task_type}, got {plan_directive.get('task_type')}."
        )

    if expected.execution_mode and plan_directive.get("execution_mode") != expected.execution_mode:
        failures.append(
            f"Expected execution_mode={expected.execution_mode}, "
            f"got {plan_directive.get('execution_mode')}."
        )

    if expected.should_call_tools is not None:
        actual = plan_directive.get("should_call_tools")
        if actual != expected.should_call_tools:
            failures.append(
                f"Expected should_call_tools={expected.should_call_tools}, got {actual}."
            )

    if expected.should_execute_sql is not None:
        actual = plan_directive.get("should_execute_sql")
        if actual != expected.should_execute_sql:
            failures.append(
                f"Expected should_execute_sql={expected.should_execute_sql}, got {actual}."
            )

    allowed = plan_directive.get("allowed_tool_groups") or []
    for group in expected.allowed_tool_groups_contains:
        if group not in allowed:
            failures.append(f"Expected allowed_tool_groups to contain '{group}', got {allowed}.")
    for group in expected.allowed_tool_groups_not_contains:
        if group in allowed:
            failures.append(f"Expected allowed_tool_groups NOT to contain '{group}', got {allowed}.")

    return failures
