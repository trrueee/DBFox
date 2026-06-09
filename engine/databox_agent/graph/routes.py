from __future__ import annotations

from typing import Literal

from langgraph.graph import END

from engine.databox_agent.graph.state import DataBoxAgentState


def _last_tool_calls(state: DataBoxAgentState) -> list[Any]:
    messages = state.get("messages", [])
    if not messages:
        return []
    last = messages[-1]
    return list(getattr(last, "tool_calls", None) or [])


def route_planner_output(state: DataBoxAgentState) -> Literal["model", "finalize"]:
    """After planner: if clarification needed → finalize, else → model."""
    plan = state.get("plan_directive") or {}
    if plan.get("needs_clarification") or state.get("status") == "waiting_user":
        return "finalize"
    # If no tools are allowed and the planner says no tools needed, go direct to finalize
    # This handles pure chat / product_help / database_concept without entering ReAct loop
    allowed = state.get("allowed_tool_groups") or []
    plan_should_call = plan.get("should_call_tools", True)
    if not allowed or not plan_should_call:
        return "finalize"
    return "model"


def route_model_output(state: DataBoxAgentState) -> Literal["policy", "progress"]:
    """After model node: tool_calls → policy gate; otherwise → progress judge."""
    if state.get("status") in ("completed", "failed", "waiting_approval", "waiting_user"):
        return "progress"
    if _last_tool_calls(state):
        return "policy"
    return "progress"


def route_policy_output(state: DataBoxAgentState) -> Literal["tools", "approval", "model", "progress"]:
    """After policy node: route to tools, approval, model, or progress on denial."""
    if state.get("status") in ("completed", "failed", "waiting_user"):
        return "progress"
    if state.get("status") == "waiting_approval" or state.get("pending_approval"):
        return "approval"
    if state.get("allowed_tool_calls"):
        return "tools"
    # blocked → model for retry, unless consecutive block limit reached
    if state.get("consecutive_blocks", 0) > 2:
        return "progress"
    return "model"


def route_approval_output(state: DataBoxAgentState) -> Literal["tools", "model", "progress"]:
    """After approval interrupt: approved + calls → tools; rejected → model; else → progress."""
    approval = state.get("approval_result") or {}
    if approval.get("status") == "approved" and state.get("allowed_tool_calls"):
        return "tools"
    if approval.get("status") == "rejected":
        return "model"
    return "progress"


def route_progress_output(state: DataBoxAgentState) -> Literal["model", "planner", "finalize"]:
    """After progress judge: complete/clarify/blocked/failed → finalize;
    continue → model; replan → planner (with anti-loop limit)."""
    decision = state.get("progress_decision") or {}
    status = decision.get("status", "failed")

    if status == "complete":
        return "finalize"
    if status == "continue":
        return "model"
    if status == "replan":
        replan_count = int(state.get("replan_count", 0))
        if replan_count < 2:
            return "planner"
        # Replan limit exceeded — force finalize
        return "finalize"
    # clarify / blocked / failed → finalize
    return "finalize"
