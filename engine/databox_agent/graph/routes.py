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


def route_model_output(state: DataBoxAgentState) -> Literal["policy", "finalize"]:
    """After model node: tool_calls → policy gate; otherwise → finalize."""
    if _last_tool_calls(state):
        return "policy"
    return "finalize"


def route_policy_output(state: DataBoxAgentState) -> Literal["tools", "approval", "model"]:
    """After policy node: route to tools, approval, or back to model."""
    if state.get("status") == "waiting_approval" or state.get("pending_approval"):
        return "approval"
    if state.get("allowed_tool_calls"):
        return "tools"
    return "model"


def route_approval_output(state: DataBoxAgentState) -> Literal["tools", "model", "finalize"]:
    """After approval interrupt: approved + calls → tools; rejected → model."""
    approval = state.get("approval_result") or {}
    if approval.get("status") == "approved" and state.get("allowed_tool_calls"):
        return "tools"
    if approval.get("status") == "rejected":
        return "model"
    return "finalize"


def route_observe_output(state: DataBoxAgentState) -> Literal["model", "finalize"]:
    """After observe: go back to model, unless terminal or step limit reached."""
    if state.get("status") in ("completed", "failed"):
        return "finalize"
    if int(state.get("step_count", 0)) >= int(state.get("max_steps", 20)):
        return "finalize"
    return "model"
