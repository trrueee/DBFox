from __future__ import annotations

import importlib.util
from collections.abc import Callable
from typing import Any, Hashable, cast

from engine.agent_kernel.state import KernelState

LangGraphStateGraph: Any
try:
    from langgraph.graph import END, START, StateGraph as _LangGraphStateGraph

    LangGraphStateGraph = _LangGraphStateGraph
except ImportError:  # pragma: no cover - exercised only when optional runtime is absent.
    END = "__end__"
    START = "__start__"
    LangGraphStateGraph = None


GraphNode = Callable[[KernelState], dict[str, Any]]


def langgraph_available() -> bool:
    return importlib.util.find_spec("langgraph") is not None


def build_agent_kernel_graph(
    *,
    controller_node: GraphNode,
    policy_node: GraphNode,
    execute_tool_node: GraphNode,
    ingest_message_node: GraphNode | None = None,
    approval_interrupt_node: GraphNode | None = None,
    checkpointer: Any | None = None,
) -> Any:
    if LangGraphStateGraph is None:
        raise RuntimeError("LangGraph is not installed; install `langgraph` to build AgentKernelGraph.")

    graph = cast(Any, LangGraphStateGraph)(KernelState)
    graph.add_node("ingest_message", cast(Any, ingest_message_node or _noop_node))
    graph.add_node("controller", cast(Any, controller_node))
    graph.add_node("policy", cast(Any, policy_node))
    graph.add_node("execute_tool", cast(Any, execute_tool_node))
    if approval_interrupt_node is not None:
        graph.add_node("approval_interrupt", cast(Any, approval_interrupt_node))

    graph.add_edge(START, "ingest_message")
    graph.add_edge("ingest_message", "controller")
    graph.add_conditional_edges(
        "controller",
        _after_controller,
        {
            "policy": "policy",
            "controller": "controller",
            "end": END,
        },
    )

    policy_routes: dict[Hashable, str] = {
        "execute_tool": "execute_tool",
        "controller": "controller",
        "end": END,
    }
    if approval_interrupt_node is not None:
        policy_routes["approval_interrupt"] = "approval_interrupt"
    graph.add_conditional_edges("policy", _after_policy, policy_routes)

    if approval_interrupt_node is not None:
        graph.add_conditional_edges(
            "approval_interrupt",
            _after_approval,
            {
                "execute_tool": "execute_tool",
                "end": END,
            },
        )

    graph.add_edge("execute_tool", "controller")
    return graph.compile(checkpointer=checkpointer)


def _noop_node(_state: KernelState) -> dict[str, Any]:
    return {"status": "running"}


def _after_controller(state: KernelState) -> str:
    decision = state.get("pending_decision") or {}
    if decision.get("action") == "call_tool":
        return "policy"
    if decision.get("action") == "update_plan":
        return "controller"
    return "end"


def _after_policy(state: KernelState) -> str:
    if state.get("status") == "waiting_approval":
        return "approval_interrupt"
    if state.get("pending_tool_call"):
        return "execute_tool"
    if state.get("error"):
        return "controller"
    return "controller"


def _after_approval(state: KernelState) -> str:
    return "execute_tool" if state.get("pending_tool_call") else "end"
