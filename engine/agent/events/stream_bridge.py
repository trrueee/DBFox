from __future__ import annotations

import json
from typing import Any

from engine.agent.app.runtime_config import AgentRuntimeEvent


def format_sse_event(event: AgentRuntimeEvent) -> str:
    """Format an AgentRuntimeEvent as an SSE (Server-Sent Events) string."""
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def graph_update_to_events(
    node_name: str,
    update: dict[str, Any],
    run_id: str,
) -> list[dict[str, Any]]:
    """Convert a single graph node update into a list of event dicts.

    Used by service.py to emit events from graph stream chunks.
    """
    events: list[dict[str, Any]] = []
    trace_events = update.get("trace_events") or []

    for te in trace_events:
        if not isinstance(te, dict):
            continue
        events.append({
            "node": node_name,
            "run_id": run_id,
            "type": te.get("type", "agent.trace"),
            "payload": te,
        })

    return events


def build_error_sse_event(event_type: str, error_message: str, code: str = "AGENT_ERROR") -> str:
    """Build an SSE error event string for exception handling in stream endpoints."""
    payload = json.dumps({
        "event_id": "error",
        "run_id": "",
        "sequence": 1,
        "created_at_ms": 0,
        "type": event_type,
        "error": error_message,
        "response": None,
        "code": code,
    })
    return f"event: {event_type}\ndata: {payload}\n\n"
