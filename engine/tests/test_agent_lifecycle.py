from __future__ import annotations

from engine.agent_kernel.lifecycle import classify_intent, plan_route, reflect, resolve_context
from engine.agent_kernel.graph import build_agent_kernel_graph, langgraph_available


def test_lifecycle_classifies_sql_revision_from_existing_context() -> None:
    state = {
        "messages": [{"role": "user", "content": "把刚才的 SQL 改成按月统计"}],
        "workspace_context": {"active_sql": "SELECT DATE(created_at), total FROM orders"},
        "execute": False,
    }

    assert classify_intent(state) == "revise_sql"
    route = plan_route({**state, "agent_intent": {"intent": "revise_sql"}})
    assert route["route"] == ["sql.revise", "sql.validate", "answer.synthesize"]
    assert route["is_review_only"] is True


def test_lifecycle_context_and_reflection_are_structured() -> None:
    state = {
        "datasource_id": "ds-1",
        "messages": [{"role": "user", "content": "查一下 GMV"}],
        "sql": "SELECT SUM(total_amount) FROM orders",
        "safety": {"can_execute": False, "blocked_reasons": ["unknown_column"]},
        "artifacts": [{"id": "sql_candidate"}],
    }

    context = resolve_context(state)
    reflection = reflect(state)

    assert context["datasource_id"] == "ds-1"
    assert context["has_sql"] is True
    assert context["has_safety"] is True
    assert context["artifact_count"] == 1
    assert reflection["action"] == "revise_or_explain_block"


def test_agent_kernel_graph_exposes_lifecycle_nodes() -> None:
    if not langgraph_available():
        return

    graph = build_agent_kernel_graph(
        controller_node=lambda _state: {"pending_decision": {"action": "final_answer"}, "status": "completed"},
        policy_node=lambda _state: {},
        execute_tool_node=lambda _state: {},
    )

    assert graph is not None
