from __future__ import annotations

from typing import Any
from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig

from engine.databox_agent.graph.state import DataBoxAgentState


def approval_interrupt(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Suspend the graph and wait for human approval via LangGraph interrupt().

    The interrupt value carries the pending approval context so the caller
    (service.py) can present it to the user. When resumed with Command(resume=...),
    the return value of interrupt() is the user's decision.
    """
    pending = state.get("pending_approval") or {}

    decision = interrupt({
        "type": "approval_required",
        "approval": pending,
        "message": "This action requires human approval before the agent can continue.",
    })

    # decision is the value passed via Command(resume=...)
    if isinstance(decision, dict) and decision.get("decision") == "approved":
        requested = pending.get("requested_action") if isinstance(pending, dict) else {}
        # Build id from pending approval context so DataBoxToolNode can use call["id"]
        call_id = (
            (pending.get("tool_call_id") if isinstance(pending, dict) else None)
            or f"approved_{pending.get('id', 'unknown')}"
        )
        approved_tool_call = {
            "name": str(requested.get("tool_name") or pending.get("tool_name") or ""),
            "args": dict(requested.get("args") or {}),
            "id": str(call_id),
        }
        return {
            "status": "running",
            "pending_approval": None,
            "approval_result": {"status": "approved", "note": decision.get("note")},
            "allowed_tool_calls": [approved_tool_call],
            "trace_events": [
                {"type": "agent.approval.approved", "approval_id": pending.get("id")}
            ],
        }

    # rejected or unknown
    return {
        "status": "running",
        "pending_approval": None,
        "approval_result": {
            "status": "rejected",
            "note": decision.get("note") if isinstance(decision, dict) else "",
        },
        "allowed_tool_calls": [],
        "trace_events": [
            {"type": "agent.approval.rejected", "approval_id": pending.get("id")}
        ],
    }
