from __future__ import annotations

from engine.agent_kernel.graph import (
    _after_observe,
    _new_data_question_node,
    _route_intent,
    _revise_sql_node,
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


def test_new_data_question_branch_starts_with_schema_tool() -> None:
    state = _with_intent({"messages": [{"role": "user", "content": "查询订单 GMV"}]})

    update = _new_data_question_node(state)

    assert update["agent_graph_route"] == "policy"
    assert update["pending_tool_call"]["tool_name"] == "schema.build_context"


def test_new_data_question_routes_to_sql_critic_after_generation() -> None:
    state = _with_intent(
        {
            "messages": [{"role": "user", "content": "查询订单 GMV"}],
            "schema_context": {"schema_context": "orders(id, gmv)"},
            "query_plan": {"candidate_tables": ["orders"]},
            "sql": "SELECT SUM(gmv) FROM orders",
        }
    )

    update = _new_data_question_node(state)

    assert update["agent_graph_route"] == "sql_critic"


def test_observe_routes_sql_generation_to_sql_critic() -> None:
    state = {"last_tool_name": "sql.generate", "last_observation": {"status": "success"}}

    assert _after_observe(state) == "sql_critic"


def test_revise_branch_validates_after_revision_attempt() -> None:
    state = _with_intent(
        {
            "messages": [{"role": "user", "content": "把刚才 SQL 改成按月统计"}],
            "sql": "SELECT strftime('%Y-%m', created_at), SUM(total) FROM orders GROUP BY 1",
            "revision_attempted": True,
        }
    )

    update = _revise_sql_node(state)

    assert update["pending_tool_call"]["tool_name"] == "sql.validate"
