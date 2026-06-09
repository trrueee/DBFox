from __future__ import annotations

from collections.abc import Callable
from typing import Any

from engine.agent_kernel.state import KernelState

GraphNode = Callable[[KernelState], dict[str, Any]]

MAX_SQL_REVISIONS = 3
MAX_TRANSIENT_RETRIES = 3
RETRY_BACKOFF_BASE_MS = 250
RETRY_BACKOFF_MAX_MS = 2_000


# -- helpers ---------------------------------------------------------------


def _intent(state: KernelState) -> str:
    payload = state.get("agent_intent") if isinstance(state.get("agent_intent"), dict) else {}
    return str(payload.get("intent") or "new_data_question")


def _has_tool_call(state: KernelState) -> bool:
    return bool(state.get("pending_tool_call"))


def _call(tool_name: str, args: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "status": "running",
        "pending_tool_call": {"tool_name": tool_name, "args": args, "reason": reason},
        "trace_events": [{"type": "agent.graph.tool", "payload": {"tool_name": tool_name, "reason": reason}}],
    }


def _route_trace(route: str, reason: str) -> dict[str, Any]:
    return {
        "status": "running",
        "trace_events": [{"type": "agent.graph.route", "payload": {"route": route, "reason": reason}}],
    }


def _go(route: str, reason: str) -> dict[str, Any]:
    return _route_trace(route, reason)


def _answer(answer: str, reason: str) -> dict[str, Any]:
    payload = {
        "answer": answer,
        "key_findings": [],
        "evidence": [],
        "caveats": [],
        "recommendations": [],
        "follow_up_questions": [],
    }
    return {
        "status": "completed",
        "agent_graph_route": "answer",
        "answer": payload,
        "final_answer": payload,
        "trace_events": [{"type": "agent.graph.answer", "payload": {"reason": reason}}],
    }
