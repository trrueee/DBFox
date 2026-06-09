from __future__ import annotations

from collections.abc import Callable
from typing import Any, Hashable

from engine.agent_kernel.graph_shared import _intent
from engine.agent_kernel.lifecycle import resolve_reference
from engine.agent_kernel.state import KernelState


INTENT_ROUTE_MAP: dict[str, str | Callable[[KernelState], str]] = {
    "new_data_question": "build_schema_context",
    "revise_sql": "revise_sql",
    "explain_sql": "explain_sql",
    "approval_help": "approval_help",
    "followup_on_result": lambda state: (
        "load_followup_context"
        if state.get("follow_up_context") and not state.get("followup_context")
        else "profile_result"
    ),
    "chart_request": "chart_request",
    "clarification": "clarification",
}


def _route_intent_node(state: KernelState) -> dict[str, Any]:
    route = _route_intent(state)
    return {
        "agent_graph_route": route,
        "trace_events": [
            {
                "type": "agent.route_intent",
                "payload": {
                    "intent": _intent(state),
                    "route": route,
                    "reference": resolve_reference(state),
                },
            }
        ],
    }


def _route_intent(state: KernelState) -> str:
    intent = _intent(state)
    route = INTENT_ROUTE_MAP.get(intent)
    if isinstance(route, str):
        return route
    if callable(route):
        return route(state)
    return "controller"


def _route_intent_routes() -> dict[Hashable, str]:
    return {
        "build_schema_context": "build_schema_context",
        "revise_sql": "revise_sql",
        "explain_sql": "explain_sql",
        "approval_help": "approval_help",
        "load_followup_context": "load_followup_context",
        "profile_result": "profile_result",
        "chart_request": "chart_request",
        "clarification": "clarification",
        "controller": "controller",
    }
