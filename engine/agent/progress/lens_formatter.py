from __future__ import annotations

from typing import Any
from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.message_utils import first_user_text


def enrich_progress_result(result: dict[str, Any], state: DBFoxAgentState) -> dict[str, Any]:
    """Attach visible_plan (Task Lens) and bump revision_count on repair continue."""
    decision_raw = result.get("progress_decision") or {}
    if not isinstance(decision_raw, dict):
        return result

    plan = state.get("plan_directive") or {}
    user_text = first_user_text(state.get("messages", []))
    visible = {
        "goal": plan.get("reasoning_summary") or user_text[:120] or "Agent task",
        "current_focus": (
            decision_raw.get("user_visible_update")
            or decision_raw.get("next_action_hint")
            or decision_raw.get("reason_summary")
            or ""
        ),
        "next_likely": decision_raw.get("next_action_hint") or "",
        "missing_evidence": decision_raw.get("missing_evidence") or [],
    }
    result["visible_plan"] = visible

    recovery = decision_raw.get("recovery_strategy")
    next_groups = decision_raw.get("next_tool_groups") or []
    if decision_raw.get("status") == "continue" and (recovery or next_groups):
        if recovery:
            result["revision_count"] = int(state.get("revision_count") or 0) + 1
        if next_groups:
            current_groups = list(state.get("allowed_tool_groups") or [])
            merged = list(dict.fromkeys(current_groups + list(next_groups)))
            result["allowed_tool_groups"] = merged
            result["repair_mode"] = True

    return result
