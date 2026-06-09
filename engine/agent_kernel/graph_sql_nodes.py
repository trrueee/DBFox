from __future__ import annotations

from typing import Any

from engine.agent_kernel.graph_retry import (
    _error_telemetry,
    _is_sql_or_db_semantic_error,
    _reference_sql,
    _revision_count,
    _revision_reason,
)
from engine.agent_kernel.graph_shared import (
    MAX_SQL_REVISIONS,
    MAX_TRANSIENT_RETRIES,
    RETRY_BACKOFF_BASE_MS,
    RETRY_BACKOFF_MAX_MS,
    _answer,
    _call,
    _go,
    _has_tool_call,
    _route_trace,
)
from engine.agent_kernel.lifecycle import resolve_reference
from engine.agent_kernel.state import KernelState, latest_user_message


# -- SQL workflow nodes ----------------------------------------------------


def _build_schema_context_node(state: KernelState) -> dict[str, Any]:
    if state.get("schema_context"):
        return _go("generate_sql", "Schema context already exists.")
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
        return _answer(
            "I could not produce a safe SQL after multiple revision attempts. "
            "Please clarify the metric, table, or filter you want to use.",
            "Max SQL revision attempts reached.",
        )
    sql = state.get("sql") or _reference_sql(state)
    if not sql:
        return _answer(
            "I need an existing SQL statement before I can revise it.",
            "No SQL reference was available for revision.",
        )
    return _call(
        "sql.revise",
        {"sql": sql, "user_instruction": latest_user_message(state), "error": _revision_reason(state)},
        "Revise SQL from critic, validation, execution, or user instruction.",
    )


def _validate_sql_node(state: KernelState) -> dict[str, Any]:
    if state.get("safety"):
        return _go("validation_route", "SQL safety result already exists.")
    return _call("sql.validate", {"sql": state.get("sql")}, "Validate SQL before execution.")


def _validation_route_node(state: KernelState) -> Any:
    from langgraph.types import Command

    safety = state.get("safety") if isinstance(state.get("safety"), dict) else {}
    if not safety:
        return Command(update=_route_trace("validate_sql", "Missing validation result."), goto="validate_sql")
    if safety.get("can_execute"):
        return Command(update=_route_trace("execution_decision", "SQL passed TrustGate."), goto="execution_decision")
    blocked = [str(reason) for reason in safety.get("blocked_reasons", [])]
    hard_blockers = [reason for reason in blocked if reason != "requires_confirmation"]
    if hard_blockers and _revision_count(state) < MAX_SQL_REVISIONS:
        return Command(update=_route_trace("revise_sql", "TrustGate blocked SQL; revise."), goto="revise_sql")
    if safety.get("requires_confirmation") and not hard_blockers:
        return Command(update=_route_trace("execution_decision", "SQL requires approval before execution."), goto="execution_decision")
    return Command(update=_route_trace("synthesize_answer", "Explain why SQL cannot be executed safely."), goto="synthesize_answer")


def _execution_decision_node(state: KernelState) -> Any:
    from langgraph.types import Command

    if state.get("execute", True):
        return Command(update=_route_trace("execute_sql", "Execution enabled."), goto="execute_sql")
    return Command(update=_route_trace("skip_execution", "Execution disabled by request."), goto="skip_execution")


def _execute_sql_node(_state: KernelState) -> dict[str, Any]:
    return _call("sql.execute_readonly", {}, "Execute validated read-only SQL through PolicyGate.")


def _skip_execution_node(_state: KernelState) -> dict[str, Any]:
    return _call("sql.skip_execution", {}, "Record review-only execution skip.")


def _execution_result_route_node(state: KernelState) -> Any:
    from langgraph.types import Command

    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    telemetry = _error_telemetry(state)
    if telemetry and telemetry.get("retryable"):
        return Command(update=_route_trace("transient_retry", "Execution failed with retryable telemetry."), goto="transient_retry")
    if telemetry and _is_sql_or_db_semantic_error(state) and _revision_count(state) < MAX_SQL_REVISIONS:
        return Command(update=_route_trace("revise_sql", "Execution failed with non-retryable SQL/DB error; revise SQL."), goto="revise_sql")
    if not execution:
        return Command(update=_route_trace("execution_decision", "Missing execution result."), goto="execution_decision")
    if execution.get("success") is False and _revision_count(state) < MAX_SQL_REVISIONS:
        return Command(update=_route_trace("revise_sql", "Execution failed; revise SQL."), goto="revise_sql")
    if execution.get("success") is False:
        return Command(update=_route_trace("synthesize_answer", "Explain execution failure after retry limit."), goto="synthesize_answer")
    return Command(update=_route_trace("profile_result", "Execution succeeded."), goto="profile_result")


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


def _chart_request_node(state: KernelState) -> Any:
    from langgraph.types import Command

    if not state.get("execution") and not state.get("result_profile"):
        return Command(
            update={
                "status": "running",
                "trace_events": [{
                    "type": "agent.graph.route",
                    "payload": {"route": "synthesize_answer", "reason": "Chart request has no result context."},
                }],
            },
            goto="synthesize_answer",
        )
    return Command(
        update={
            "status": "running",
            "trace_events": [{
                "type": "agent.graph.route",
                "payload": {"route": "chart_suggest", "reason": "Chart request uses existing result context."},
            }],
        },
        goto="chart_suggest",
    )


def _explain_sql_node(state: KernelState) -> dict[str, Any]:
    sql = state.get("sql") or _reference_sql(state)
    if not sql:
        return _answer("I could not find a current SQL statement to explain.", "No SQL reference was available.")
    return _answer(
        "This request is about the SQL already in context, so I am not starting a new data-question flow or executing the query.\n\n"
        f"```sql\n{sql}\n```",
        "Explain SQL branch answered directly from resolved SQL context.",
    )


def _approval_help_node(state: KernelState) -> dict[str, Any]:
    approval = state.get("pending_approval") or {}
    reference = resolve_reference(state)
    approval_id = approval.get("id") if isinstance(approval, dict) else reference.get("id")
    return _answer(
        "This run is waiting for approval before the pending action can continue. "
        "I will not simulate approval or execute the pending action in chat. "
        f"Approval reference: {approval_id or 'current approval context'}.",
        "Approval help branch explained pending approval without execution.",
    )


def _clarification_node(_state: KernelState) -> dict[str, Any]:
    return {
        "status": "waiting_user",
        "pending_decision": {"action": "ask_user", "user_message": "I need a bit more detail before I can continue."},
        "trace_events": [{"type": "agent.ask_user", "payload": {"reason": "Clarification branch selected."}}],
    }


# -- Conditional edge functions --------------------------------------------


def _after_build_schema_context(state: KernelState) -> str:
    return "policy" if _has_tool_call(state) else "generate_sql"


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
