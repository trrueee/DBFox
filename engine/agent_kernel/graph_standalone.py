from __future__ import annotations

import importlib.util
from collections.abc import Callable
from typing import Any, Hashable, cast

from engine.agent_kernel.lifecycle import answer_node, context_node, reflect_node, resolve_reference, understand_node
from engine.agent_kernel.state import KernelState, latest_user_message

# -- leaf modules (no internal deps) ---------------------------------------
from engine.agent_kernel.graph_shared import (  # noqa: F401  # re-exported
    MAX_SQL_REVISIONS,
    MAX_TRANSIENT_RETRIES,
    RETRY_BACKOFF_BASE_MS,
    RETRY_BACKOFF_MAX_MS,
    GraphNode,
    _answer,
    _call,
    _go,
    _has_tool_call,
    _intent,
    _route_trace,
)

# -- retry helpers ---------------------------------------------------------
from engine.agent_kernel.graph_retry import (  # noqa: F401  # re-exported
    _can_retry_transient,
    _error_telemetry,
    _failed_tool_name,
    _is_sql_or_db_semantic_error,
    _reference_sql,
    _revision_count,
    _revision_reason,
)

# -- intent routing --------------------------------------------------------
from engine.agent_kernel.graph_intent import (  # noqa: F401  # re-exported
    INTENT_ROUTE_MAP,
    _route_intent,
    _route_intent_node,
    _route_intent_routes,
)

# -- observation -----------------------------------------------------------
from engine.agent_kernel.graph_observation import (  # noqa: F401  # re-exported
    TOOL_FALLBACK_ROUTE_MAP,
    _after_observe,
    _after_sql_critic,
    _observe_node,
    _observe_routes,
)

# -- SQL workflow nodes + conditional edges --------------------------------
from engine.agent_kernel.graph_sql_nodes import (  # noqa: F401  # re-exported
    _after_approval,
    _after_build_query_plan,
    _after_build_schema_context,
    _after_chart_suggest,
    _after_controller,
    _after_followup_suggest,
    _after_generate_sql,
    _after_load_followup_context,
    _after_policy,
    _after_profile_result,
    _after_revise_sql,
    _after_synthesize_answer,
    _after_transient_retry,
    _after_validate_sql,
    _approval_help_node,
    _build_query_plan_node,
    _build_schema_context_node,
    _chart_request_node,
    _chart_suggest_node,
    _clarification_node,
    _execute_sql_node,
    _execution_decision_node,
    _execution_result_route_node,
    _explain_sql_node,
    _followup_suggest_node,
    _generate_sql_node,
    _load_followup_context_node,
    _profile_result_node,
    _revise_sql_node,
    _skip_execution_node,
    _synthesize_answer_node,
    _transient_retry_node,
    _validate_sql_node,
    _validation_route_node,
)

LangGraphStateGraph: Any
try:
    from langgraph.graph import END, START, StateGraph as _LangGraphStateGraph

    LangGraphStateGraph = _LangGraphStateGraph
except ImportError:  # pragma: no cover
    END = "__end__"
    START = "__start__"
    LangGraphStateGraph = None


def langgraph_available() -> bool:
    return importlib.util.find_spec("langgraph") is not None


def _noop_node(_state: KernelState) -> dict[str, Any]:
    return {"status": "running"}


# -- graph composition -------------------------------------------------------


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

    from langgraph.cache.memory import InMemoryCache

    graph = cast(Any, LangGraphStateGraph)(KernelState)

    graph.add_node("ingest_message", cast(Any, ingest_message_node or _noop_node))
    graph.add_node("understand", cast(Any, understand_node))
    graph.add_node("context", cast(Any, context_node))
    graph.add_node("route_intent", cast(Any, _route_intent_node))

    graph.add_node("explain_sql", cast(Any, _explain_sql_node))
    graph.add_node("approval_help", cast(Any, _approval_help_node))
    graph.add_node("clarification", cast(Any, _clarification_node))

    graph.add_node("build_schema_context", cast(Any, _build_schema_context_node))
    graph.add_node("build_query_plan", cast(Any, _build_query_plan_node))
    graph.add_node("generate_sql", cast(Any, _generate_sql_node))
    graph.add_node("sql_critic", cast(Any, reflect_node))
    graph.add_node("revise_sql", cast(Any, _revise_sql_node))
    graph.add_node("validate_sql", cast(Any, _validate_sql_node))
    graph.add_node("validation_route", cast(Any, _validation_route_node))
    graph.add_node("execution_decision", cast(Any, _execution_decision_node))
    graph.add_node("execute_sql", cast(Any, _execute_sql_node))
    graph.add_node("skip_execution", cast(Any, _skip_execution_node))
    graph.add_node("execution_result_route", cast(Any, _execution_result_route_node))
    graph.add_node("transient_retry", cast(Any, _transient_retry_node))
    graph.add_node("profile_result", cast(Any, _profile_result_node))
    graph.add_node("chart_suggest", cast(Any, _chart_suggest_node))
    graph.add_node("followup_suggest", cast(Any, _followup_suggest_node))
    graph.add_node("synthesize_answer", cast(Any, _synthesize_answer_node))
    graph.add_node("load_followup_context", cast(Any, _load_followup_context_node))
    graph.add_node("chart_request", cast(Any, _chart_request_node))

    graph.add_node("controller", cast(Any, controller_node))
    graph.add_node("policy", cast(Any, policy_node))
    graph.add_node("execute_tool", cast(Any, execute_tool_node))
    graph.add_node("observe", cast(Any, _observe_node))
    graph.add_node("answer", cast(Any, answer_node))
    if approval_interrupt_node is not None:
        graph.add_node("approval_interrupt", cast(Any, approval_interrupt_node))

    graph.add_edge(START, "ingest_message")
    graph.add_edge("ingest_message", "understand")
    graph.add_edge("understand", "context")
    graph.add_edge("context", "route_intent")
    graph.add_conditional_edges("route_intent", _route_intent, _route_intent_routes())

    graph.add_conditional_edges("build_schema_context", _after_build_schema_context, {"policy": "policy", "build_query_plan": "build_query_plan"})
    graph.add_conditional_edges("build_query_plan", _after_build_query_plan, {"policy": "policy", "generate_sql": "generate_sql"})
    graph.add_conditional_edges("generate_sql", _after_generate_sql, {"policy": "policy", "sql_critic": "sql_critic"})
    graph.add_conditional_edges("revise_sql", _after_revise_sql, {"policy": "policy", "answer": "answer"})
    graph.add_conditional_edges("validate_sql", _after_validate_sql, {"policy": "policy", "validation_route": "validation_route"})
    graph.add_edge("execute_sql", "policy")
    graph.add_edge("skip_execution", "policy")
    graph.add_conditional_edges("transient_retry", _after_transient_retry, {"policy": "policy", "synthesize_answer": "synthesize_answer"})
    graph.add_conditional_edges("profile_result", _after_profile_result, {"policy": "policy", "chart_suggest": "chart_suggest", "synthesize_answer": "synthesize_answer"})
    graph.add_conditional_edges("chart_suggest", _after_chart_suggest, {"policy": "policy", "followup_suggest": "followup_suggest"})
    graph.add_conditional_edges("followup_suggest", _after_followup_suggest, {"policy": "policy", "synthesize_answer": "synthesize_answer"})
    graph.add_conditional_edges("synthesize_answer", _after_synthesize_answer, {"policy": "policy", "answer": "answer"})
    graph.add_conditional_edges("load_followup_context", _after_load_followup_context, {"policy": "policy", "profile_result": "profile_result"})

    controller_routes: dict[Hashable, str] = {"policy": "policy", "route_intent": "route_intent", "answer": "answer", "end": END}
    if approval_interrupt_node is not None:
        controller_routes["approval_interrupt"] = "approval_interrupt"
    graph.add_conditional_edges("controller", _after_controller, controller_routes)

    policy_routes: dict[Hashable, str] = {"execute_tool": "execute_tool", "revise_sql": "revise_sql", "synthesize_answer": "synthesize_answer", "answer": "answer", "end": END}
    if approval_interrupt_node is not None:
        policy_routes["approval_interrupt"] = "approval_interrupt"
    graph.add_conditional_edges("policy", _after_policy, policy_routes)

    if approval_interrupt_node is not None:
        graph.add_conditional_edges("approval_interrupt", _after_approval, {"execute_tool": "execute_tool", "answer": "answer", "end": END})

    graph.add_edge("execute_tool", "observe")
    graph.add_conditional_edges("observe", _after_observe, _observe_routes())
    graph.add_conditional_edges("sql_critic", _after_sql_critic, {"revise_sql": "revise_sql", "validate_sql": "validate_sql", "synthesize_answer": "synthesize_answer", "answer": "answer"})
    graph.add_edge("answer", END)
    return graph.compile(checkpointer=checkpointer, cache=InMemoryCache())
