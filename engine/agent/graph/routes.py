from __future__ import annotations

from typing import Any, Literal

from engine.agent.graph.state import DataBoxAgentState
from engine.agent.graph.message_utils import message_tool_calls


def _last_tool_calls(state: DataBoxAgentState) -> list[Any]:
    messages = state.get("messages", [])
    if not messages:
        return []
    return message_tool_calls(messages[-1])


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


def route_progress_output(state: DataBoxAgentState) -> Literal["model", "finalize", "repair"]:
    """After progress judge: complete/clarify → finalize; continue → model
    (model receives progress guidance); replan → model with anti-loop check;
    repair → repair."""
    decision = state.get("progress_decision") or {}
    status = decision.get("status", "failed")

    if status == "complete":
        return "finalize"
    if status == "clarify":
        return "finalize"
    if status == "replan":
        # Anti-loop: if replan budget is exhausted, finalize instead.
        from engine.agent.graph.replan_policy import allow_replan
        if not allow_replan(state, decision):
            return "finalize"
        if decision.get("recovery_strategy") or state.get("repair_mode"):
            return "repair"
        return "model"
    if status == "continue":
        if decision.get("recovery_strategy") or state.get("repair_mode"):
            return "repair"
        return "model"
    # blocked / failed → finalize
    return "finalize"
