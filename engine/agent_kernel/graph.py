from __future__ import annotations

import importlib.util
from collections.abc import Callable
from typing import Any, Hashable, cast

from engine.agent_kernel.lifecycle import (
    answer_node,
    context_node,
    observe_node,
    plan_node,
    reflect_node,
    understand_node,
)
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
    """Build the DataBox Agent Kernel graph.

    The graph now exposes the seven Agent lifecycle phases explicitly:

    1. ingest_message / understand: read the user message and classify intent.
    2. context: resolve reusable workspace, artifact, SQL, approval, and result context.
    3. plan: create a route skeleton for the controller.
    4. act: controller -> policy -> execute_tool invokes exactly one tool.
    5. observe: normalize the latest tool observation into state.
    6. reflect: decide whether the controller should continue, revise, wait, or answer.
    7. answer: mark the final answer trace before END.

    The existing controller, PolicyGate, ToolRegistry, checkpoint, approval, and
    artifact machinery stay intact. This change makes the graph semantics visible
    instead of hiding the whole Agent loop inside the controller.
    """

    if LangGraphStateGraph is None:
        raise RuntimeError("LangGraph is not installed; install `langgraph` to build AgentKernelGraph.")

    graph = cast(Any, LangGraphStateGraph)(KernelState)
    graph.add_node("ingest_message", cast(Any, ingest_message_node or _noop_node))
    graph.add_node("understand", cast(Any, understand_node))
    graph.add_node("context", cast(Any, context_node))
    graph.add_node("plan", cast(Any, plan_node))
    graph.add_node("controller", cast(Any, controller_node))
    graph.add_node("policy", cast(Any, policy_node))
    graph.add_node("execute_tool", cast(Any, execute_tool_node))
    graph.add_node("observe", cast(Any, observe_node))
    graph.add_node("reflect", cast(Any, reflect_node))
    graph.add_node("answer", cast(Any, answer_node))
    if approval_interrupt_node is not None:
        graph.add_node("approval_interrupt", cast(Any, approval_interrupt_node))

    graph.add_edge(START, "ingest_message")
    graph.add_edge("ingest_message", "understand")
    graph.add_edge("understand", "context")
    graph.add_edge("context", "plan")
    graph.add_edge("plan", "controller")
    graph.add_conditional_edges(
        "controller",
        _after_controller,
        {
            "policy": "policy",
            "controller": "controller",
            "answer": "answer",
            "end": END,
        },
    )

    policy_routes: dict[Hashable, str] = {
        "execute_tool": "execute_tool",
        "controller": "controller",
        "answer": "answer",
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
                "answer": "answer",
                "end": END,
            },
        )

    graph.add_edge("execute_tool", "observe")
    graph.add_edge("observe", "reflect")
    graph.add_edge("reflect", "controller")
    graph.add_edge("answer", END)
    return graph.compile(checkpointer=checkpointer)


def _noop_node(_state: KernelState) -> dict[str, Any]:
    return {"status": "running"}


def _after_controller(state: KernelState) -> str:
    decision = state.get("pending_decision") or {}
    if decision.get("action") == "call_tool":
        return "policy"
    if decision.get("action") == "update_plan":
        return "controller"
    if decision.get("action") in {"final_answer", "ask_user", "pause", "wait_approval"}:
        return "answer"
    return "end"


def _after_policy(state: KernelState) -> str:
    if state.get("status") == "waiting_approval":
        return "approval_interrupt"
    if state.get("pending_tool_call"):
        return "execute_tool"
    if state.get("error"):
        return "controller"
    if state.get("status") in {"completed", "failed", "paused", "waiting_user"}:
        return "answer"
    return "controller"


def _after_approval(state: KernelState) -> str:
    if state.get("pending_tool_call"):
        return "execute_tool"
    return "answer"
