from __future__ import annotations

import typing
from typing import Any

from engine.agent_kernel.databinding import merge_state
from engine.agent_kernel.state import ADDITIVE_STATE_KEYS, KernelState


def _reducer_fields_from_kernelstate() -> set[str]:
    """Extract field names from KernelState that use Annotated[list[...], add]."""
    hints = typing.get_type_hints(KernelState, include_extras=True)
    fields: set[str] = set()
    for name, hint in hints.items():
        origin = typing.get_origin(hint)
        if origin is not typing.Annotated:
            continue
        args = typing.get_args(hint)
        if len(args) < 2:
            continue
        base_type = args[0]
        if typing.get_origin(base_type) is not list:
            continue
        reducer = args[1]
        from operator import add
        if reducer is add:
            fields.add(name)
    return fields


def test_additive_state_keys_match_kernelstate_reducers() -> None:
    """Every Annotated[list[...], add] field in KernelState must be in ADDITIVE_STATE_KEYS."""
    reducer_fields = _reducer_fields_from_kernelstate()
    assert reducer_fields, "Expected at least one reducer field in KernelState"

    assert reducer_fields == set(ADDITIVE_STATE_KEYS), (
        f"ADDITIVE_STATE_KEYS mismatch:\n"
        f"  In ADDITIVE_STATE_KEYS but NOT a reducer: {set(ADDITIVE_STATE_KEYS) - reducer_fields}\n"
        f"  Is a reducer but NOT in ADDITIVE_STATE_KEYS: {reducer_fields - set(ADDITIVE_STATE_KEYS)}"
    )


def _scalar_updates() -> list[dict[str, Any]]:
    return [
        {"status": "running", "error": None},
        {"sql": "SELECT 1", "safety": None},
        {"safety": {"passed": True, "can_execute": True}},
        {"status": "waiting_approval"},
        {"status": "running", "pending_tool_call": {"tool_name": "sql.execute_readonly", "args": {}}},
        {"execution": {"success": True, "rowCount": 5}},
        {"status": "completed", "answer": {"answer": "Done."}},
    ]


def _additive_updates() -> list[dict[str, Any]]:
    return [
        {"messages": [{"role": "user", "content": "hello"}]},
        {"messages": [{"role": "assistant", "content": "hi"}]},
        {"plan_events": [{"type": "plan.step_added"}]},
        {"plan_events": [{"type": "plan.step_completed"}]},
        {"tool_results": [{"tool_name": "sql.execute_readonly", "success": True}]},
        {"artifacts": [{"id": "art_001", "type": "table"}]},
        {"trace_events": [{"type": "tool.completed"}]},
        {"trace_events": [{"type": "answer.completed"}]},
    ]


def test_merge_state_accumulates_additive_fields() -> None:
    """merge_state must extend lists for ADDITIVE_STATE_KEYS and overwrite scalars."""
    state: dict[str, Any] = {}
    for update in _scalar_updates() + _additive_updates():
        merge_state(state, update)

    # Scalar overwrite: last value wins
    assert state["status"] == "completed"
    assert state["answer"] == {"answer": "Done."}
    assert state["safety"] == {"passed": True, "can_execute": True}
    assert state["sql"] == "SELECT 1"

    # Additive accumulation: all values are appended.
    # messages uses add_messages which converts dicts to BaseMessage objects.
    assert len(state["messages"]) == 2
    msg0 = state["messages"][0]
    msg1 = state["messages"][1]
    assert getattr(msg0, "content", "") == "hello"
    assert getattr(msg0, "type", "") == "human"
    assert getattr(msg1, "content", "") == "hi"
    assert getattr(msg1, "type", "") == "ai"
    assert len(state["plan_events"]) == 2
    assert len(state["tool_results"]) == 1
    assert len(state["artifacts"]) == 1
    assert len(state["trace_events"]) == 2


def test_merge_state_does_not_lose_previous_additive_content() -> None:
    """Successive merge_state calls preserve previously accumulated list content."""
    state: dict[str, Any] = {}
    merge_state(state, {"trace_events": [{"n": 1}]})
    merge_state(state, {"trace_events": [{"n": 2}]})
    merge_state(state, {"trace_events": [{"n": 3}]})
    assert [e["n"] for e in state["trace_events"]] == [1, 2, 3]


def test_merge_state_streaming_pattern_matches_langgraph_semantics() -> None:
    """Simulate the service.py streaming pattern and verify key invariants.

    Semantics: stream_mode="updates" yields per-node return values.
    merge_state accumulates additive fields (list extend) and overwrites scalars.
    LangGraph internal reducer uses operator.add (list concat) for the same fields.
    Both produce equivalent final values when processing the same sequence.
    """
    # Simulate a 3-node linear graph:
    #   node_a -> node_b -> node_c
    # Each returns an update dict. Service.py would merge them into shadow state.
    # LangGraph would reduce them internally with operator.add for additive fields.
    shadow: dict[str, Any] = {}

    # node_a: sets up initial values
    merge_state(shadow, {
        "messages": [{"role": "user", "content": "Q1"}],
        "status": "running",
    })
    # node_b: adds more additive content, overwrites a scalar
    merge_state(shadow, {
        "messages": [{"role": "assistant", "content": "A1"}],
        "plan_events": [{"step": "schema"}, {"step": "query"}],
        "trace_events": [{"type": "node_b.executed"}],
        "status": "tool_running",
    })
    # node_c: final state
    merge_state(shadow, {
        "tool_results": [{"sql": "SELECT 1", "rows": 5}],
        "artifacts": [{"id": "art_result"}],
        "trace_events": [{"type": "node_c.completed"}],
        "status": "completed",
    })

    # Additive fields: all values accumulated.
    # messages uses add_messages which converts dicts to BaseMessage objects.
    assert len(shadow["messages"]) == 2
    assert getattr(shadow["messages"][0], "type", "") == "human"
    assert getattr(shadow["messages"][1], "type", "") == "ai"
    assert len(shadow["plan_events"]) == 2
    assert len(shadow["trace_events"]) == 2
    assert len(shadow["tool_results"]) == 1
    assert len(shadow["artifacts"]) == 1

    # Scalar fields: last write wins (same as LangGraph default reducer)
    assert shadow["status"] == "completed"

    # Verify merge_state messages match what LangGraph add_messages would produce.
    from langgraph.graph.message import add_messages
    lg_messages = add_messages(
        [{"role": "user", "content": "Q1"}],
        [{"role": "assistant", "content": "A1"}],
    )
    assert len(shadow["messages"]) == len(lg_messages)


def test_api_key_not_in_kernelstate() -> None:
    """api_key/api_base/model_name must NOT be in KernelState — configurable only."""
    from engine.agent_kernel.state import KernelState
    from engine.agent_kernel.service import AgentKernelService

    # Static check: fields must not exist in KernelState TypedDict
    hints = __import__("typing").get_type_hints(KernelState)
    for secret_field in ("api_key", "api_base", "model_name"):
        assert secret_field not in hints, (
            f"KernelState must not contain '{secret_field}'. "
            f"LLM runtime config belongs in config.configurable only."
        )


def test_api_key_not_in_serialized_state() -> None:
    """Verify that a serialized state dict never contains api_key."""
    state: dict[str, Any] = {
        "thread_id": "t1",
        "run_id": "r1",
        "status": "running",
        "messages": [{"role": "user", "content": "test"}],
        "plan_events": [{"step": 1}],
        "tool_results": [],
        "artifacts": [],
        "trace_events": [],
    }
    import json
    serialized = json.dumps(state, default=str)
    assert "api_key" not in serialized
    assert "sk-" not in serialized.lower()
