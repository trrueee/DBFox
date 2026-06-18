from __future__ import annotations

from typing import Any

from engine.agent_core.types import ToolObservation


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_tool_result_to_state(
    *,
    state: dict[str, Any],
    tool_name: str,
    observation: ToolObservation,
    merge_strategy: str = "reuse",
) -> dict[str, Any]:
    from engine.tools.runtime.state_reducer import apply_tool_observation_to_state

    return apply_tool_observation_to_state(
        state=state,
        tool_name=tool_name,
        observation=observation,
        merge_strategy=merge_strategy,
    )


# ---------------------------------------------------------------------------
# State merging (for streaming event view)
# ---------------------------------------------------------------------------

ADDITIVE_STATE_KEYS: frozenset[str] = frozenset({
    "plan_events",
    "tool_results",
    "artifacts",
    "trace_events",
})

MESSAGE_STATE_KEY: str = "messages"


def merge_state(state: dict[str, Any], update: dict[str, Any]) -> None:
    """Accumulate node updates into a streaming event view (NOT source of truth)."""
    for key, value in update.items():
        if key == MESSAGE_STATE_KEY:
            from langgraph.graph.message import add_messages
            current = state.get(key, [])
            state[key] = add_messages(current, value)
        elif key in ADDITIVE_STATE_KEYS:
            current = state.setdefault(key, [])
            if isinstance(current, list) and isinstance(value, list):
                current.extend(value)
            else:
                state[key] = value
        else:
            state[key] = value
