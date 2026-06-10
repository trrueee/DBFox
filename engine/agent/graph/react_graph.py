from __future__ import annotations

from typing import Any
from langgraph.graph import END, START, StateGraph

from engine.agent.graph.state import DataBoxAgentState
from engine.agent.graph.routes import (
    route_planner_output,
    route_model_output,
    route_policy_output,
    route_approval_output,
    route_progress_output,
)


def build_databox_react_graph(*, checkpointer=None) -> Any:
    """Build the DataBox Agent ReAct graph.

    Flow:
        START → planner → model → policy → tools → observe → progress → ...
        progress can route to: model (continue), planner (replan), finalize (done).

    The Planner decides task intent, tool scope, and execution mode.
    The Model (ReAct) executes with dynamically scoped tools.
    PolicyGate enforces hard safety boundaries.
    The Progress Judge determines completion / continuation / replanning.
    """
    from engine.agent.nodes.planner_node import create_plan
    from engine.agent.nodes.model_node import call_model
    from engine.agent.nodes.policy_node import apply_policy
    from engine.agent.nodes.tool_node import execute_allowed_tools
    from engine.agent.nodes.observe_node import observe_tools
    from engine.agent.nodes.progress_node import judge_progress
    from engine.agent.nodes.finalize_node import finalize_answer
    from engine.agent.nodes.approval_node import approval_interrupt

    graph = StateGraph(DataBoxAgentState)

    # ---- Nodes -----------------------------------------------------------
    graph.add_node("planner", create_plan)
    graph.add_node("model", call_model)
    graph.add_node("policy", apply_policy)
    graph.add_node("tools", execute_allowed_tools)
    graph.add_node("observe", observe_tools)
    graph.add_node("progress", judge_progress)
    graph.add_node("approval", approval_interrupt)
    graph.add_node("finalize", finalize_answer)

    # ---- Edges -----------------------------------------------------------
    graph.add_edge(START, "planner")

    graph.add_conditional_edges(
        "planner",
        route_planner_output,
        {
            "model": "model",
            "finalize": "finalize",
        },
    )

    graph.add_conditional_edges(
        "model",
        route_model_output,
        {
            "policy": "policy",
            "progress": "progress",
        },
    )

    graph.add_conditional_edges(
        "policy",
        route_policy_output,
        {
            "tools": "tools",
            "approval": "approval",
            "model": "model",
            "progress": "progress",
        },
    )

    graph.add_conditional_edges(
        "approval",
        route_approval_output,
        {
            "tools": "tools",
            "model": "model",
            "progress": "progress",
        },
    )

    graph.add_edge("tools", "observe")
    graph.add_edge("observe", "progress")

    graph.add_conditional_edges(
        "progress",
        route_progress_output,
        {
            "model": "model",
            "planner": "planner",
            "finalize": "finalize",
        },
    )

    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
