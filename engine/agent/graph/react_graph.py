from __future__ import annotations

from typing import Any
from langgraph.graph import END, START, StateGraph

from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.routes import (
    route_model_output,
    route_policy_output,
    route_approval_output,
    route_progress_output,
)


def build_dbfox_react_graph(*, checkpointer=None) -> Any:
    """Build the DBFox Agent ReAct graph — pure ReAct loop with state-machine guarantees.

    Flow:
        START → model → policy → tools → observe → progress → model/repair/finalize

    The Model decides every action by observing state (messages, tool results,
    environment).  There is no separate Planner — the ReAct loop IS the plan.

    Graph provides state-machine guarantees only:
      - Step limit (model_node hard block + progress_node fast path)
      - Checkpoint / resume (LangGraph checkpointer + approval interrupts)
      - Anti-loop (replan budget, consecutive block limit)
      - Policy gate (safety boundary enforcement)
    """
    from engine.agent.nodes.model_node import call_model
    from engine.agent.nodes.policy_node import apply_policy
    from engine.agent.nodes.tool_node import execute_allowed_tools
    from engine.agent.nodes.observe_node import observe_tools
    from engine.agent.nodes.progress_node import judge_progress
    from engine.agent.nodes.prepare_repair_node import prepare_repair
    from engine.agent.nodes.finalize_node import finalize_answer
    from engine.agent.nodes.approval_node import approval_interrupt

    graph = StateGraph(DBFoxAgentState)

    # ---- Nodes -----------------------------------------------------------
    graph.add_node("model", call_model)
    graph.add_node("policy", apply_policy)
    graph.add_node("tools", execute_allowed_tools)
    graph.add_node("observe", observe_tools)
    graph.add_node("progress", judge_progress)
    graph.add_node("repair", prepare_repair)
    graph.add_node("approval", approval_interrupt)
    graph.add_node("finalize", finalize_answer)

    # ---- Edges -----------------------------------------------------------
    graph.add_edge(START, "model")

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
            "repair": "repair",
            "finalize": "finalize",
        },
    )

    graph.add_edge("repair", "model")

    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
