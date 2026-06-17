from __future__ import annotations

from typing import Any
from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig

from engine.agent.graph.state import DBFoxAgentState


def _safety_after_approval(safety: Any) -> dict[str, Any] | None:
    """Lift the confirmation gate from the TrustGate safety state after a human
    approved the action, so re-execution does not block on the stale decision."""
    if not isinstance(safety, dict) or not safety:
        return None
    updated = dict(safety)
    updated["requires_confirmation"] = False
    updated["can_execute"] = True
    updated["blocked_reasons"] = [
        r for r in (updated.get("blocked_reasons") or []) if r != "requires_confirmation"
    ]
    decision = updated.get("execution_safety_decision")
    if isinstance(decision, dict) and decision:
        decision = dict(decision)
        decision["requires_confirmation"] = False
        decision["can_execute"] = True
        decision["approved_by_user"] = True
        decision["blocked_reasons"] = [
            r for r in (decision.get("blocked_reasons") or []) if r != "requires_confirmation"
        ]
        if not decision.get("blocked_reasons"):
            decision["passed"] = True
        if not str(decision.get("safe_sql") or "").strip():
            guardrail = decision.get("guardrail") if isinstance(decision.get("guardrail"), dict) else {}
            decision["safe_sql"] = (
                str(guardrail.get("safeSql") or "").strip()
                or str(updated.get("safe_sql") or "").strip()
                or str(decision.get("original_sql") or "").strip()
                or None
            )
        updated["execution_safety_decision"] = decision
    return updated


def approval_interrupt(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
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
        # Build id from pending approval context so DBFoxToolNode can use call["id"]
        call_id = (
            (pending.get("tool_call_id") if isinstance(pending, dict) else None)
            or f"approved_{pending.get('id', 'unknown')}"
        )
        approved_tool_call = {
            "name": str(requested.get("tool_name") or pending.get("tool_name") or ""),
            "args": dict(requested.get("args") or {}),
            "id": str(call_id),
        }
        updates: dict[str, Any] = {
            "status": "running",
            "pending_approval": None,
            "approval_result": {"status": "approved", "note": decision.get("note")},
            "allowed_tool_calls": [approved_tool_call],
            "trace_events": [
                {"type": "agent.approval.approved", "approval_id": pending.get("id")}
            ],
        }
        approved_safety = _safety_after_approval(state.get("safety"))
        if approved_safety is not None:
            updates["safety"] = approved_safety
        return updates

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
