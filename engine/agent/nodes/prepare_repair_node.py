"""Prepare repair sub-path — runs before model when SQL self-healing is active."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from engine.agent.graph.state import DataBoxAgentState


def prepare_repair(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Repair subgraph entry: consolidate tool scope and record repair attempt metrics.

    Lightweight — no LLM.  Progress Judge already chose recovery_strategy;
    this node ensures the model turn starts with repair context and trace.
    """
    progress = state.get("progress_decision") or {}
    repair_trace = state.get("repair_trace") or []

    attempts = int(state.get("revision_count") or 0)
    last_repair = repair_trace[-1] if repair_trace else {}
    error_class = last_repair.get("error_class") if isinstance(last_repair, dict) else None

    groups = list(state.get("allowed_tool_groups") or [])
    for g in progress.get("next_tool_groups") or []:
        if g not in groups:
            groups.append(g)

    repair_stats = {
        "attempts": attempts,
        "max_attempts": 3,
        "last_error_class": error_class,
        "recovery_strategy": progress.get("recovery_strategy"),
        "active": True,
    }

    trace: dict[str, Any] = {
        "type": "agent.repair.prepared",
        "attempt": attempts,
        "error_class": error_class,
        "tool_groups": groups,
        "recovery_strategy": progress.get("recovery_strategy"),
    }

    return {
        "allowed_tool_groups": groups,
        "repair_mode": True,
        "revision_attempted": True,
        "repair_stats": repair_stats,
        "trace_events": [trace],
    }
