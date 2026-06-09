from __future__ import annotations

from typing import Any
from langgraph.graph import END, START, StateGraph

from engine.databox_agent.graph.state import DataBoxAgentState
from engine.databox_agent.nodes.model_node import call_model
from engine.databox_agent.nodes.policy_node import apply_policy
from engine.databox_agent.nodes.tool_node import DataBoxToolNode
from engine.databox_agent.nodes.observe_node import observe_tools
from engine.databox_agent.nodes.finalize_node import finalize_answer
from engine.databox_agent.nodes.approval_node import approval_interrupt
from engine.databox_agent.graph.routes import (
    route_model_output,
    route_policy_output,
    route_approval_output,
)


def build_databox_react_graph(*, checkpointer=None) -> Any:
    graph = StateGraph(DataBoxAgentState)

    graph.add_node("model", call_model)
    graph.add_node("policy", apply_policy)
    graph.add_node("tools", DataBoxToolNode)
    graph.add_node("observe", observe_tools)
    graph.add_node("approval", approval_interrupt)
    graph.add_node("finalize", finalize_answer)

    graph.add_edge(START, "model")

    graph.add_conditional_edges(
        "model",
        route_model_output,
        {
            "policy": "policy",
            "finalize": "finalize",
        },
    )

    graph.add_conditional_edges(
        "policy",
        route_policy_output,
        {
            "tools": "tools",
            "approval": "approval",
            "model": "model",
        },
    )

    graph.add_conditional_edges(
        "approval",
        route_approval_output,
        {
            "tools": "tools",
            "model": "model",
            "finalize": "finalize",
        },
    )

    graph.add_edge("tools", "observe")
    graph.add_edge("observe", "model")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
