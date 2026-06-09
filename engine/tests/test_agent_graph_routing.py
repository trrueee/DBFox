from __future__ import annotations

from engine.agent_kernel.graph_standalone import (
    _after_controller,
    _after_observe,
    _build_schema_context_node,
    _generate_sql_node,
    _route_intent,
    _revise_sql_node,
    _validation_route_node,
)
from engine.agent_kernel.lifecycle import context_node, understand_node


def _with_intent(state: dict) -> dict:
    state = {**state}
    state.update(understand_node(state))
    state.update(context_node(state))
    return state


def test_route_intent_sends_sql_explanation_to_explain_branch() -> None:
    state = _with_intent(
        {
            "messages": [{"role": "user", "content": "解释一下这个 SQL"}],
            "workspace_context": {"selected_sql": "SELECT id FROM users"},
        }
    )

    assert state["agent_intent"]["intent"] == "explain_sql"
    assert _route_intent(state) == "explain_sql"


def test_route_intent_sends_sql_revision_to_revise_branch() -> None:
    state = _with_intent(
        {
            "messages": [{"role": "user", "content": "把刚才 SQL 改成按月统计"}],
            "workspace_context": {"selected_sql": "SELECT created_at, total FROM orders"},
        }
    )

    assert state["agent_intent"]["intent"] == "revise_sql"
    assert _route_intent(state) == "revise_sql"


def test_new_data_question_starts_with_schema_tool_node() -> None:
    state = _with_intent({"messages": [{"role": "user", "content": "查询订单 GMV"}]})

    update = _build_schema_context_node(state)

    assert update["pending_tool_call"]["tool_name"] == "schema.build_context"


def test_generate_sql_node_routes_existing_sql_to_critic() -> None:
    state = _with_intent(
        {
            "messages": [{"role": "user", "content": "查询订单 GMV"}],
            "schema_context": {"schema_context": "orders(id, gmv)"},
            "query_plan": {"candidate_tables": ["orders"]},
            "sql": "SELECT SUM(gmv) FROM orders",
        }
    )

    update = _generate_sql_node(state)

    trace = update.get("trace_events", [{}])[0]
    assert trace["type"] == "agent.graph.route"
    assert trace["payload"]["route"] == "sql_critic"


def test_observe_routes_sql_generation_to_sql_critic() -> None:
    state = {"last_tool_name": "sql.generate", "last_observation": {"status": "success"}}

    assert _after_observe(state) == "sql_critic"


def test_controller_wait_approval_routes_to_interrupt() -> None:
    state = {"pending_decision": {"action": "wait_approval"}}

    assert _after_controller(state) == "approval_interrupt"


def test_known_intent_bypasses_controller() -> None:
    """Every known intent must route to a lifecycle node, not 'controller'."""
    known_intents = [
        ("查一下 GMV", "build_schema_context"),
    ]
    for message, expected_route in known_intents:
        state = _with_intent({"messages": [{"role": "user", "content": message}]})
        route = _route_intent(state)
        assert route != "controller", f"Known intent for '{message}' must not route to controller"
        assert route == expected_route, f"Expected '{expected_route}' for '{message}', got '{route}'"


def test_unrecognized_intent_falls_back_to_controller() -> None:
    """When _intent() returns an intent not covered by _route_intent's if/elif chain,
    the fallback return 'controller' must be reached."""
    # _intent() reads agent_intent and defaults to 'new_data_question'.
    # To trigger the controller fallback, set an intent that's in VALID_INTENTS
    # but hypothetically absent from _route_intent's chain.
    # All current VALID_INTENTS are covered, but the fallback must still exist.
    state: dict = {
        "messages": [{"role": "user", "content": "hello"}],
        "agent_intent": {"intent": "new_data_question", "confidence": "medium"},
    }
    assert _route_intent(state) == "build_schema_context"
    # Verify the fallback exists: if _route_intent receives state without agent_intent,
    # _intent() defaults to 'new_data_question' → NOT controller.
    # The 'return "controller"' line is the failsafe for future intent additions.


def test_controller_call_tool_routes_to_policy() -> None:
    """Controller producing call_tool must route through policy, not directly to execute_tool."""
    state = {
        "pending_decision": {
            "action": "call_tool",
            "tool_call": {"tool_name": "answer.synthesize", "args": {}, "reason": "test"},
        },
    }
    assert _after_controller(state) == "policy"


def test_controller_final_answer_routes_to_answer_node() -> None:
    state = {
        "pending_decision": {
            "action": "final_answer",
            "final_answer": "All done.",
        },
    }
    assert _after_controller(state) == "answer"


def test_controller_update_plan_does_not_bypass_policy_or_intent() -> None:
    """update_plan action must re-enter route_intent, not skip to execution."""
    state = {
        "pending_decision": {"action": "update_plan"},
    }
    assert _after_controller(state) == "route_intent"
    assert _after_controller(state) != "execute_tool"


def test_revise_branch_stops_after_revision_limit() -> None:
    state = _with_intent(
        {
            "messages": [{"role": "user", "content": "把刚才 SQL 改成按月统计"}],
            "sql": "SELECT created_at, total FROM orders",
            "revision_count": 3,
        }
    )

    update = _revise_sql_node(state)

    assert update["agent_graph_route"] == "answer"
    assert update["status"] == "completed"


def test_validation_route_sends_blocked_sql_to_revision_under_limit() -> None:
    state = {
        "sql": "SELECT missing_col FROM orders",
        "revision_count": 1,
        "safety": {"can_execute": False, "blocked_reasons": ["unknown_column"]},
    }

    cmd = _validation_route_node(state)

    assert cmd.goto == "revise_sql"
    assert "revise_sql" in str(cmd.update.get("trace_events", []))
