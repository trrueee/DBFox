"""Adaptive replan budget — coding-agent style recovery without infinite loops."""

from __future__ import annotations

from typing import Any

# Per failure-layer replan allowance (on top of task-type base).
_LAYER_REPLAN_BONUS: dict[str, int] = {
    "schema": 1,
    "semantic": 1,
    "query_plan": 1,
    "sql_generation": 0,
    "sql_validation": 0,
    "execution": 0,
    "result_analysis": 0,
    "planner": -1,
    "policy": -1,
    "unknown": 0,
}

_COMPLEX_TASK_TYPES = frozenset({
    "data_lookup",
    "result_analysis",
    "semantic_analysis",
    "sql_repair",
})


def compute_max_replans(state: dict[str, Any], decision: dict[str, Any] | None = None) -> int:
    """How many replan cycles are allowed for this run state."""
    decision = decision or {}
    plan = state.get("plan_directive") or {}
    task_type = str(plan.get("task_type") or "")

    base = 3 if task_type in _COMPLEX_TASK_TYPES else 2

    failure_layer = str(decision.get("failure_layer") or "")
    base += _LAYER_REPLAN_BONUS.get(failure_layer, 0)

    # Fast-path repairs already consumed revision budget — allow one extra replan.
    if int(state.get("revision_count") or 0) > 0 and failure_layer in ("schema", "semantic", "query_plan"):
        base += 1

    return max(1, min(base, 4))


def allow_replan(state: dict[str, Any], decision: dict[str, Any]) -> bool:
    """True when progress judge requests replan and budget allows it."""
    if decision.get("status") != "replan":
        return False

    retry_budget = int(decision.get("retry_budget", 0))
    if retry_budget <= 0:
        return False

    replan_count = int(state.get("replan_count", 0))
    return replan_count < compute_max_replans(state, decision)
