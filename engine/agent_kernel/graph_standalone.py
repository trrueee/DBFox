from __future__ import annotations

import importlib.util
from collections.abc import Callable
from typing import Any, Hashable, cast

from engine.agent_kernel.lifecycle import answer_node, context_node, reflect_node, resolve_reference, understand_node
from engine.agent_kernel.state import KernelState, latest_user_message

LangGraphStateGraph: Any
try:
    from langgraph.graph import END, START, StateGraph as _LangGraphStateGraph

    LangGraphStateGraph = _LangGraphStateGraph
except ImportError:  # pragma: no cover
    END = "__end__"
    START = "__start__"
    LangGraphStateGraph = None


GraphNode = Callable[[KernelState], dict[str, Any]]
MAX_SQL_REVISIONS = 3
MAX_TRANSIENT_RETRIES = 3
RETRY_BACKOFF_BASE_MS = 250
RETRY_BACKOFF_MAX_MS = 2_000


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

    from langgraph.types import CachePolicy
    from langgraph.cache.memory import InMemoryCache

    graph = cast(Any, LangGraphStateGraph)(KernelState)

    graph.add_node("ingest_message", cast(Any, ingest_message_node or _noop_node))
    graph.add_node("understand", cast(Any, understand_node))
    graph.add_node("context", cast(Any, context_node))
    graph.add_node("route_intent", cast(Any, _route_intent_node))

    graph.add_node("explain_sql", cast(Any, _explain_sql_node))
    graph.add_node("approval_help", cast(Any, _approval_help_node))
    graph.add_node("clarification", cast(Any, _clarification_node))

    graph.add_node("build_schema_context", cast(Any, _build_schema_context_node), cache_policy=CachePolicy(ttl=600))
    graph.add_node("build_query_plan", cast(Any, _build_query_plan_node), cache_policy=CachePolicy(ttl=600))
    graph.add_node("generate_sql", cast(Any, _generate_sql_node))
    graph.add_node("sql_critic", cast(Any, reflect_node))
    graph.add_node("revise_sql", cast(Any, _revise_sql_node))
    graph.add_node("validate_sql", cast(Any, _validate_sql_node), cache_policy=CachePolicy(ttl=600))
    graph.add_node("validation_route", cast(Any, _validation_route_node))
    graph.add_node("execution_decision", cast(Any, _execution_decision_node))
    graph.add_node("execute_sql", cast(Any, _execute_sql_node))
    graph.add_node("skip_execution", cast(Any, _skip_execution_node))
    graph.add_node("execution_result_route", cast(Any, _execution_result_route_node))
    graph.add_node("transient_retry", cast(Any, _transient_retry_node))
    graph.add_node("profile_result", cast(Any, _profile_result_node), cache_policy=CachePolicy(ttl=600))
    graph.add_node("chart_suggest", cast(Any, _chart_suggest_node), cache_policy=CachePolicy(ttl=600))
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
    graph.add_conditional_edges("chart_request", _after_chart_request, {"chart_suggest": "chart_suggest", "synthesize_answer": "synthesize_answer", "answer": "answer"})

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
    graph.add_conditional_edges("validation_route", _after_validation_route, {"execution_decision": "execution_decision", "revise_sql": "revise_sql", "synthesize_answer": "synthesize_answer", "answer": "answer", "validate_sql": "validate_sql"})
    graph.add_conditional_edges("execution_decision", _after_execution_decision, {"execute_sql": "execute_sql", "skip_execution": "skip_execution", "synthesize_answer": "synthesize_answer"})
    graph.add_conditional_edges("execution_result_route", _after_execution_result_route, {"profile_result": "profile_result", "revise_sql": "revise_sql", "synthesize_answer": "synthesize_answer", "answer": "answer", "execution_decision": "execution_decision"})
    graph.add_edge("answer", END)
    return graph.compile(checkpointer=checkpointer, cache=InMemoryCache())


def _noop_node(_state: KernelState) -> dict[str, Any]:
    return {"status": "running"}


def _route_intent_node(state: KernelState) -> dict[str, Any]:
    route = _route_intent(state)
    return {"agent_graph_route": route, "trace_events": [{"type": "agent.route_intent", "payload": {"intent": _intent(state), "route": route, "reference": resolve_reference(state)}}]}


INTENT_ROUTE_MAP: dict[str, str | Callable[[KernelState], str]] = {
    "new_data_question": "build_schema_context",
    "revise_sql": "revise_sql",
    "explain_sql": "explain_sql",
    "approval_help": "approval_help",
    "followup_on_result": lambda state: "load_followup_context" if state.get("follow_up_context") and not state.get("followup_context") else "profile_result",
    "chart_request": "chart_request",
    "clarification": "clarification",
}


def _route_intent(state: KernelState) -> str:
    intent = _intent(state)
    route = INTENT_ROUTE_MAP.get(intent)
    if isinstance(route, str):
        return route
    if callable(route):
        return route(state)
    return "controller"


def _route_intent_routes() -> dict[Hashable, str]:
    return {"build_schema_context": "build_schema_context", "revise_sql": "revise_sql", "explain_sql": "explain_sql", "approval_help": "approval_help", "load_followup_context": "load_followup_context", "profile_result": "profile_result", "chart_request": "chart_request", "clarification": "clarification", "controller": "controller"}


def _build_schema_context_node(state: KernelState) -> dict[str, Any]:
    if state.get("schema_context"):
        return _go("build_query_plan", "Schema context already exists.")
    return _call("schema.build_context", {"question": latest_user_message(state)}, "Build schema context for data question.")


def _build_query_plan_node(state: KernelState) -> dict[str, Any]:
    if state.get("query_plan"):
        return _go("generate_sql", "Query plan already exists.")
    return _call("query_plan.build", {}, "Build query plan from schema context.")


def _generate_sql_node(state: KernelState) -> dict[str, Any]:
    if state.get("sql"):
        return _go("sql_critic", "SQL candidate already exists.")
    return _call("sql.generate", {}, "Generate SQL candidate.")


def _revise_sql_node(state: KernelState) -> dict[str, Any]:
    if _revision_count(state) >= MAX_SQL_REVISIONS:
        return _answer("I could not produce a safe SQL after multiple revision attempts. Please clarify the metric, table, or filter you want to use.", "Max SQL revision attempts reached.")
    sql = state.get("sql") or _reference_sql(state)
    if not sql:
        return _answer("I need an existing SQL statement before I can revise it.", "No SQL reference was available for revision.")
    return _call("sql.revise", {"sql": sql, "user_instruction": latest_user_message(state), "error": _revision_reason(state)}, "Revise SQL from critic, validation, execution, or user instruction.")


def _validate_sql_node(state: KernelState) -> dict[str, Any]:
    if state.get("safety"):
        return _go("validation_route", "SQL safety result already exists.")
    return _call("sql.validate", {"sql": state.get("sql")}, "Validate SQL before execution.")


def _validation_route_node(state: KernelState) -> dict[str, Any]:
    safety = state.get("safety") if isinstance(state.get("safety"), dict) else {}
    if not safety:
        return _go("validate_sql", "Missing validation result.")
    if safety.get("can_execute"):
        return _go("execution_decision", "SQL passed TrustGate.")
    blocked = [str(reason) for reason in safety.get("blocked_reasons", [])]
    hard_blockers = [reason for reason in blocked if reason != "requires_confirmation"]
    if hard_blockers and _revision_count(state) < MAX_SQL_REVISIONS:
        return _go("revise_sql", "TrustGate blocked SQL; revise.")
    if safety.get("requires_confirmation") and not hard_blockers:
        return _go("execution_decision", "SQL requires approval before execution.")
    return _call("answer.synthesize", {}, "Explain why SQL cannot be executed safely.")


def _execution_decision_node(state: KernelState) -> dict[str, Any]:
    return _go("execute_sql", "Execution enabled.") if state.get("execute", True) else _go("skip_execution", "Execution disabled by request.")


def _execute_sql_node(_state: KernelState) -> dict[str, Any]:
    return _call("sql.execute_readonly", {}, "Execute validated read-only SQL through PolicyGate.")


def _skip_execution_node(_state: KernelState) -> dict[str, Any]:
    return _call("sql.skip_execution", {}, "Record review-only execution skip.")


def _execution_result_route_node(state: KernelState) -> dict[str, Any]:
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    telemetry = _error_telemetry(state)
    if telemetry and telemetry.get("retryable"):
        return _go("transient_retry", "Execution failed with retryable telemetry.")
    if telemetry and _is_sql_or_db_semantic_error(state) and _revision_count(state) < MAX_SQL_REVISIONS:
        return _go("revise_sql", "Execution failed with non-retryable SQL/DB error; revise SQL.")
    if not execution:
        return _go("execution_decision", "Missing execution result.")
    if execution.get("success") is False and _revision_count(state) < MAX_SQL_REVISIONS:
        return _go("revise_sql", "Execution failed; revise SQL.")
    if execution.get("success") is False:
        return _call("answer.synthesize", {}, "Explain execution failure after retry limit.")
    return _go("profile_result", "Execution succeeded.")


def _transient_retry_node(state: KernelState) -> dict[str, Any]:
    telemetry = _error_telemetry(state)
    failed_tool_call = state.get("last_failed_tool_call") if isinstance(state.get("last_failed_tool_call"), dict) else {}
    tool_name = str(failed_tool_call.get("tool_name") or telemetry.get("tool_name") or state.get("last_tool_name") or "")
    if not tool_name or not failed_tool_call:
        return _call("answer.synthesize", {}, "Cannot retry because failed tool context is missing.")

    counters = dict(state.get("retry_counters") or {})
    current_attempts = int(counters.get(tool_name, 0))
    if current_attempts >= MAX_TRANSIENT_RETRIES:
        return {
            "status": "running",
            "error": str(state.get("error") or telemetry.get("error_type") or "Retry limit reached."),
            "pending_tool_call": None,
            "agent_graph_route": "synthesize_answer",
            "trace_events": [
                {
                    "type": "agent.retry.exhausted",
                    "payload": {"tool_name": tool_name, "attempts": current_attempts, "telemetry": telemetry},
                }
            ],
        }

    next_attempt = current_attempts + 1
    counters[tool_name] = next_attempt
    backoff_ms = min(RETRY_BACKOFF_BASE_MS * (2 ** max(next_attempt - 1, 0)), RETRY_BACKOFF_MAX_MS)
    retry_call = {"tool_name": tool_name, "args": dict(failed_tool_call.get("args") or {})}
    return {
        "status": "running",
        "error": None,
        "pending_tool_call": retry_call,
        "retry_counters": counters,
        "trace_events": [
            {
                "type": "agent.retry.scheduled",
                "payload": {"tool_name": tool_name, "attempt": next_attempt, "backoff_ms": backoff_ms, "telemetry": telemetry},
            }
        ],
    }


def _profile_result_node(state: KernelState) -> dict[str, Any]:
    if not state.get("execution") and not state.get("result_profile"):
        return _call("answer.synthesize", {}, "Answer from available context because no execution result is loaded.")
    if state.get("result_profile"):
        return _go("chart_suggest", "Result profile already exists.")
    return _call("result.profile", {}, "Profile execution result.")


def _chart_suggest_node(state: KernelState) -> dict[str, Any]:
    if state.get("chart_suggestion"):
        return _go("followup_suggest", "Chart suggestion already exists.")
    return _call("chart.suggest", {}, "Suggest chart when result context exists.")


def _followup_suggest_node(state: KernelState) -> dict[str, Any]:
    if state.get("suggestions"):
        return _go("synthesize_answer", "Follow-up suggestions already exist.")
    return _call("followup.suggest", {}, "Suggest useful follow-up questions.")


def _synthesize_answer_node(state: KernelState) -> dict[str, Any]:
    if state.get("answer"):
        return _go("answer", "Answer already exists.")
    return _call("answer.synthesize", {}, "Synthesize final answer from graph state and artifacts.")


def _load_followup_context_node(state: KernelState) -> dict[str, Any]:
    if state.get("followup_context"):
        return _go("profile_result", "Follow-up context already loaded.")
    return _call("followup.load_context", {}, "Load parent run context for follow-up.")


def _chart_request_node(state: KernelState) -> dict[str, Any]:
    if not state.get("execution") and not state.get("result_profile"):
        return _go("synthesize_answer", "Chart request has no result context.")
    return _go("chart_suggest", "Chart request uses existing result context.")


def _explain_sql_node(state: KernelState) -> dict[str, Any]:
    sql = state.get("sql") or _reference_sql(state)
    if not sql:
        return _answer("I could not find a current SQL statement to explain.", "No SQL reference was available.")
    return _answer("This request is about the SQL already in context, so I am not starting a new data-question flow or executing the query.\n\n" f"```sql\n{sql}\n```", "Explain SQL branch answered directly from resolved SQL context.")


def _approval_help_node(state: KernelState) -> dict[str, Any]:
    approval = state.get("pending_approval") or {}
    reference = resolve_reference(state)
    approval_id = approval.get("id") if isinstance(approval, dict) else reference.get("id")
    return _answer("This run is waiting for approval before the pending action can continue. I will not simulate approval or execute the pending action in chat. " f"Approval reference: {approval_id or 'current approval context'}.", "Approval help branch explained pending approval without execution.")


def _clarification_node(_state: KernelState) -> dict[str, Any]:
    return {"status": "waiting_user", "pending_decision": {"action": "ask_user", "user_message": "I need a bit more detail before I can continue."}, "trace_events": [{"type": "agent.ask_user", "payload": {"reason": "Clarification branch selected."}}]}


def _observe_node(state: KernelState) -> dict[str, Any]:
    """Normalize latest tool result into agent_observation for routing and diagnostics."""
    observation = state.get("last_observation") if isinstance(state.get("last_observation"), dict) else {}
    metadata = state.get("last_tool_metadata")
    next_route = metadata.get("next_route") if isinstance(metadata, dict) else None
    tool_name = state.get("last_tool_name")
    payload = {
        "tool_name": tool_name,
        "status": observation.get("status"),
        "has_error": bool(observation.get("error")),
        "retryable": bool(_error_telemetry(state).get("retryable")),
        "next_route": next_route,
    }
    return {"agent_observation": payload, "trace_events": [{"type": "agent.observe", "payload": payload}]}


def _has_tool_call(state: KernelState) -> bool:
    return bool(state.get("pending_tool_call"))


def _after_build_schema_context(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "build_query_plan"


def _after_build_query_plan(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "generate_sql"


def _after_generate_sql(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "sql_critic"


def _after_revise_sql(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "answer"


def _after_validate_sql(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "validation_route"


def _after_transient_retry(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "synthesize_answer"


def _after_profile_result(state: KernelState) -> str:
    if _has_tool_call(state):
        return "policy"
    return "chart_suggest" if state.get("result_profile") else "synthesize_answer"


def _after_chart_suggest(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "followup_suggest"


def _after_followup_suggest(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "synthesize_answer"


def _after_synthesize_answer(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "answer"


def _after_load_followup_context(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "profile_result"


def _after_chart_request(state: KernelState) -> str:
    route = str(state.get("agent_graph_route") or "")
    return route if route in {"chart_suggest", "synthesize_answer", "answer"} else "synthesize_answer"


def _after_controller(state: KernelState) -> str:
    decision = state.get("pending_decision") or {}
    if decision.get("action") == "call_tool":
        return "policy"
    if decision.get("action") == "update_plan":
        return "route_intent"
    if decision.get("action") == "wait_approval":
        return "approval_interrupt"
    if decision.get("action") in {"final_answer", "ask_user", "pause"}:
        return "answer"
    return "end"


def _after_policy(state: KernelState) -> str:
    if state.get("status") == "waiting_approval":
        return "approval_interrupt"
    if state.get("pending_tool_call"):
        return "execute_tool"
    if state.get("error") and state.get("sql") and _revision_count(state) < MAX_SQL_REVISIONS:
        return "revise_sql"
    if state.get("error"):
        return "synthesize_answer"
    if state.get("status") in {"completed", "failed", "paused", "waiting_user"}:
        return "answer"
    return "synthesize_answer"


def _after_approval(state: KernelState) -> str:
    return "execute_tool" if state.get("pending_tool_call") else "answer"


TOOL_FALLBACK_ROUTE_MAP: dict[str, str | Callable[[KernelState], str]] = {
    "schema.build_context": "build_query_plan",
    "query_plan.build": "generate_sql",
    "sql.generate": "sql_critic",
    "sql.revise": "sql_critic",
    "sql.validate": "validation_route",
    "sql.execute_readonly": "execution_result_route",
    "sql.skip_execution": "execution_result_route",
    "result.profile": "chart_suggest",
    "chart.suggest": lambda state: "followup_suggest" if _intent(state) == "new_data_question" else "synthesize_answer",
    "followup.suggest": "synthesize_answer",
    "followup.load_context": "profile_result",
    "answer.synthesize": "answer",
}


def _after_observe(state: KernelState) -> str:
    telemetry = _error_telemetry(state)
    if telemetry.get("retryable"):
        return "transient_retry" if _can_retry_transient(state) else "synthesize_answer"
    if telemetry and _is_sql_or_db_semantic_error(state) and state.get("sql") and _revision_count(state) < MAX_SQL_REVISIONS:
        return "revise_sql"
    if state.get("error") and state.get("sql") and _revision_count(state) < MAX_SQL_REVISIONS:
        return "revise_sql"
    if state.get("error"):
        return "synthesize_answer"
    observation = state.get("agent_observation") if isinstance(state.get("agent_observation"), dict) else {}
    next_route = observation.get("next_route")
    if isinstance(next_route, str) and next_route:
        if next_route == "followup_suggest" and _intent(state) != "new_data_question":
            return "synthesize_answer"
        return next_route
    metadata = state.get("last_tool_metadata")
    if isinstance(metadata, dict):
        next_route = metadata.get("next_route")
        if isinstance(next_route, str) and next_route:
            if next_route == "followup_suggest" and _intent(state) != "new_data_question":
                return "synthesize_answer"
            return next_route
    tool_name = str(state.get("last_tool_name") or "")
    if tool_name.startswith("workspace."):
        return "answer"
    route = TOOL_FALLBACK_ROUTE_MAP.get(tool_name)
    if isinstance(route, str):
        return route
    if callable(route):
        return route(state)
    return "synthesize_answer"


def _observe_routes() -> dict[Hashable, str]:
    return {"build_query_plan": "build_query_plan", "generate_sql": "generate_sql", "sql_critic": "sql_critic", "validation_route": "validation_route", "execution_result_route": "execution_result_route", "transient_retry": "transient_retry", "profile_result": "profile_result", "chart_suggest": "chart_suggest", "followup_suggest": "followup_suggest", "synthesize_answer": "synthesize_answer", "revise_sql": "revise_sql", "answer": "answer"}


def _after_sql_critic(state: KernelState) -> str:
    reflection = state.get("agent_reflection") if isinstance(state.get("agent_reflection"), dict) else {}
    critique = reflection.get("sql_critique") if isinstance(reflection.get("sql_critique"), dict) else state.get("agent_sql_critique")
    if isinstance(critique, dict) and critique.get("needs_revision"):
        return "revise_sql" if _revision_count(state) < MAX_SQL_REVISIONS else "synthesize_answer"
    return "validate_sql"


def _after_validation_route(state: KernelState) -> str:
    route = str(state.get("agent_graph_route") or "")
    if route in {"execution_decision", "revise_sql", "synthesize_answer", "answer", "validate_sql"}:
        return route
    # Fallback direct state checks
    safety = state.get("safety") if isinstance(state.get("safety"), dict) else {}
    if not safety:
        return "validate_sql"
    if safety.get("can_execute") or safety.get("requires_confirmation"):
        return "execution_decision"
    if _revision_count(state) < MAX_SQL_REVISIONS:
        return "revise_sql"
    return "synthesize_answer"


def _after_execution_decision(state: KernelState) -> str:
    route = str(state.get("agent_graph_route") or "")
    if route in {"execute_sql", "skip_execution", "synthesize_answer"}:
        return route
    # Fallback direct state checks
    return "execute_sql" if state.get("execute", True) else "skip_execution"


def _after_execution_result_route(state: KernelState) -> str:
    route = str(state.get("agent_graph_route") or "")
    if route in {"profile_result", "revise_sql", "synthesize_answer", "answer", "execution_decision", "transient_retry"}:
        return route
    # Fallback direct state checks
    telemetry = _error_telemetry(state)
    if telemetry.get("retryable"):
        return "transient_retry" if _can_retry_transient(state) else "synthesize_answer"
    if telemetry and _is_sql_or_db_semantic_error(state) and state.get("sql") and _revision_count(state) < MAX_SQL_REVISIONS:
        return "revise_sql"
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    if not execution:
        return "execution_decision"
    if execution.get("success") is False:
        return "revise_sql" if _revision_count(state) < MAX_SQL_REVISIONS else "synthesize_answer"
    return "profile_result"


def _intent(state: KernelState) -> str:
    payload = state.get("agent_intent") if isinstance(state.get("agent_intent"), dict) else {}
    return str(payload.get("intent") or "new_data_question")


def _call(tool_name: str, args: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"status": "running", "pending_tool_call": {"tool_name": tool_name, "args": args, "reason": reason}, "trace_events": [{"type": "agent.graph.tool", "payload": {"tool_name": tool_name, "reason": reason}}]}


def _go(route: str, reason: str) -> dict[str, Any]:
    return {"status": "running", "agent_graph_route": route, "trace_events": [{"type": "agent.graph.route", "payload": {"route": route, "reason": reason}}]}


def _answer(answer: str, reason: str) -> dict[str, Any]:
    payload = {"answer": answer, "key_findings": [], "evidence": [], "caveats": [], "recommendations": [], "follow_up_questions": []}
    return {"status": "completed", "agent_graph_route": "answer", "answer": payload, "final_answer": payload, "trace_events": [{"type": "agent.graph.answer", "payload": {"reason": reason}}]}


def _error_telemetry(state: KernelState) -> dict[str, Any]:
    telemetry = state.get("last_error_telemetry")
    return telemetry if isinstance(telemetry, dict) else {}


def _failed_tool_name(state: KernelState) -> str:
    failed_tool_call = state.get("last_failed_tool_call") if isinstance(state.get("last_failed_tool_call"), dict) else {}
    telemetry = _error_telemetry(state)
    return str(failed_tool_call.get("tool_name") or telemetry.get("tool_name") or state.get("last_tool_name") or "")


def _can_retry_transient(state: KernelState) -> bool:
    tool_name = _failed_tool_name(state)
    if not tool_name:
        return False
    counters = state.get("retry_counters") if isinstance(state.get("retry_counters"), dict) else {}
    return int(counters.get(tool_name, 0)) < MAX_TRANSIENT_RETRIES


def _is_sql_or_db_semantic_error(state: KernelState) -> bool:
    telemetry = _error_telemetry(state)
    tool_name = _failed_tool_name(state)
    error_type = str(telemetry.get("error_type") or "").lower()
    if tool_name in {"sql.execute_readonly", "sql.validate"}:
        return True
    semantic_tokens = ("sql", "database", "dbapi", "programmingerror", "operationalerror", "databaseerror", "syntax", "sqlite")
    return any(token in error_type for token in semantic_tokens)


def _reference_sql(state: KernelState) -> str | None:
    reference = resolve_reference(state)
    sql_preview = reference.get("sql_preview")
    return sql_preview.strip() if isinstance(sql_preview, str) and sql_preview.strip() else None


def _revision_reason(state: KernelState) -> str:
    reflection = state.get("agent_reflection") if isinstance(state.get("agent_reflection"), dict) else {}
    critique = reflection.get("sql_critique") if isinstance(reflection.get("sql_critique"), dict) else state.get("agent_sql_critique")
    if isinstance(critique, dict) and critique.get("issues"):
        return "; ".join(str(issue) for issue in critique.get("issues", []))
    telemetry = _error_telemetry(state)
    if telemetry:
        return str(telemetry.get("error_type") or state.get("error") or "Tool execution failed.")
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    return str(execution.get("revise_suggestion") or state.get("error") or latest_user_message(state) or "Revise SQL.")


def _revision_count(state: KernelState) -> int:
    value = state.get("revision_count")
    if isinstance(value, int):
        return value
    return 1 if state.get("revision_attempted") else 0
