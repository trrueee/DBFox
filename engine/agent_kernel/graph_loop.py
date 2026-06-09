from __future__ import annotations
import importlib.util
from typing import Any, Hashable, cast
from engine.agent_kernel.lifecycle import answer_node, context_node, understand_node
from engine.agent_kernel.state import KernelState
from engine.agent_kernel.planner import plan_agent_loop
from engine.agent_kernel.action_selector import select_next_action
from engine.agent_kernel.observer import observe_agent_loop
from engine.agent_kernel.reflector import decide_reflection
from engine.agent_kernel.graph_shared import GraphNode

LangGraphStateGraph: Any
try:
    from langgraph.graph import END, START, StateGraph as _LangGraphStateGraph
    LangGraphStateGraph = _LangGraphStateGraph
except ImportError:
    END = "__end__"
    START = "__start__"
    LangGraphStateGraph = None


def _noop_node(_state: KernelState) -> dict[str, Any]:
    return {"status": "running"}


def _after_act(state: KernelState) -> str:
    return "policy" if state.get("pending_tool_call") else "reflect"


def _after_policy_loop(state: KernelState) -> str:
    if state.get("status") == "waiting_approval":
        return "approval_interrupt"
    if state.get("pending_tool_call"):
        return "execute_tool"
    return "reflect"


def _after_reflect_loop(state: KernelState) -> str:
    raw_decision = state.get("reflect_decision") or {}
    decision = raw_decision.get("decision", "continue")
    if decision in ("continue", "retry"):
        return "act"
    if decision in ("replan", "revise"):
        return "plan"
    if decision == "approval":
        return "approval_interrupt"
    return "answer"


def _after_approval_loop(state: KernelState) -> str:
    return "execute_tool" if state.get("pending_tool_call") else "reflect"


def build_agent_loop_graph(
    *,
    policy_node: GraphNode,
    execute_tool_node: GraphNode,
    ingest_message_node: GraphNode | None = None,
    approval_interrupt_node: GraphNode | None = None,
    checkpointer: Any | None = None,
) -> Any:
    if LangGraphStateGraph is None:
        raise RuntimeError("LangGraph is not installed.")

    from langgraph.cache.memory import InMemoryCache

    graph = cast(Any, LangGraphStateGraph)(KernelState)

    graph.add_node("ingest_message", cast(Any, ingest_message_node or _noop_node))
    graph.add_node("understand", cast(Any, understand_node))
    graph.add_node("context", cast(Any, context_node))
    graph.add_node("plan", cast(Any, plan_agent_loop))
    graph.add_node("act", cast(Any, select_next_action))
    graph.add_node("policy", cast(Any, policy_node))
    graph.add_node("execute_tool", cast(Any, execute_tool_node))
    graph.add_node("observe", cast(Any, observe_agent_loop))
    graph.add_node("reflect", cast(Any, decide_reflection))
    graph.add_node("answer", cast(Any, answer_node))

    if approval_interrupt_node is not None:
        graph.add_node("approval_interrupt", cast(Any, approval_interrupt_node))

    graph.add_edge(START, "ingest_message")
    graph.add_edge("ingest_message", "understand")
    graph.add_edge("understand", "context")
    graph.add_edge("context", "plan")
    graph.add_edge("plan", "act")
    
    graph.add_conditional_edges("act", _after_act, {"policy": "policy", "reflect": "reflect"})
    
    policy_routes = {"execute_tool": "execute_tool", "reflect": "reflect"}
    if approval_interrupt_node is not None:
        policy_routes["approval_interrupt"] = "approval_interrupt"
    graph.add_conditional_edges("policy", _after_policy_loop, policy_routes)
    
    graph.add_edge("execute_tool", "observe")
    graph.add_edge("observe", "reflect")
    
    reflect_routes = {"act": "act", "plan": "plan", "answer": "answer"}
    if approval_interrupt_node is not None:
        reflect_routes["approval_interrupt"] = "approval_interrupt"
    graph.add_conditional_edges("reflect", _after_reflect_loop, reflect_routes)
    
    if approval_interrupt_node is not None:
        graph.add_conditional_edges("approval_interrupt", _after_approval_loop, {"execute_tool": "execute_tool", "reflect": "reflect"})

    graph.add_edge("answer", END)
    
    return graph.compile(checkpointer=checkpointer, cache=InMemoryCache())
