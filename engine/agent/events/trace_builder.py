from __future__ import annotations

from typing import Any


def build_trace_event(event_type: str, **kwargs: Any) -> dict[str, Any]:
    """Build a trace event dict for the trace_events list in state."""
    return {"type": event_type, **kwargs}


def tool_started(tool_name: str) -> dict[str, Any]:
    return build_trace_event("agent.tool.started", tool_name=tool_name)


def tool_completed(tool_name: str, status: str, latency_ms: int = 0) -> dict[str, Any]:
    return build_trace_event(
        "agent.tool.completed",
        tool_name=tool_name,
        status=status,
        latency_ms=latency_ms,
    )


def model_completed(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    return build_trace_event("agent.model.completed", tool_calls=tool_calls)


def policy_allowed(tool_names: list[str]) -> dict[str, Any]:
    return build_trace_event("agent.policy.allowed", tool_names=tool_names)


def policy_blocked(count: int) -> dict[str, Any]:
    return build_trace_event("agent.policy.blocked", count=count)


def approval_required(tool_name: str, reason: str, approval_id: str | None = None) -> dict[str, Any]:
    return build_trace_event(
        "agent.approval.required",
        tool_name=tool_name,
        reason=reason,
        approval_id=approval_id,
    )


def finalized(status: str, has_answer: bool = False, has_error: bool = False) -> dict[str, Any]:
    return build_trace_event(
        "agent.finalized",
        status=status,
        has_answer=has_answer,
        has_error=has_error,
    )
