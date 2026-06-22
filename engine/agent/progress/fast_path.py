from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.message_utils import is_ai_message, message_content_text, message_tool_calls
from engine.agent.progress.schemas import ProgressDecision
from engine.agent.graph.message_utils import first_user_text

logger = logging.getLogger("dbfox.dbfox_agent.progress.fast_path")


def _arg_signature(tool_name: str, args: dict[str, Any]) -> str:
    """Deterministic hash signature for tool name + canonical args.

    Used by loop prevention to detect identical tool invocations across steps
    even when dict ordering or minor formatting differs.
    """
    canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(f"{tool_name}::{canonical}".encode()).hexdigest()[:16]
    return digest


def _max_steps_reason(state: DBFoxAgentState, max_steps: int) -> str:
    execution = state.get("execution")
    if isinstance(execution, dict):
        if execution.get("success"):
            return f"Agent reached max_steps ({max_steps}) after query execution."
        return f"Agent reached max_steps ({max_steps}) after query execution failed."

    if state.get("sql"):
        return f"Agent reached max_steps ({max_steps}) after SQL generation."

    if not state.get("safety"):
        return "Agent stopped before SQL validation because max_steps was reached."

    return f"Agent exceeded max_steps ({max_steps})."


def check_escalate(state: DBFoxAgentState) -> dict[str, Any] | None:
    """Fast-path: detect escalate.tool_group and expand allowed_tool_groups.

    When the model calls escalate.tool_group, we immediately expand the
    tool scope and return continue — no LLM judge needed.
    """
    last_results = state.get("last_tool_results") or []
    if not last_results:
        return None

    for result in last_results:
        if not isinstance(result, dict):
            continue
        if result.get("name") != "escalate.tool_group":
            continue

        output = result.get("output") or {}
        if not output.get("escalated"):
            return {
                "progress_decision": progress_decision_dict(
                    status="continue",
                    reason_summary="Escalate called but group already available — continuing.",
                ),
                "trace_events": [{
                    "type": "agent.progress.judged",
                    "status": "continue",
                    "reason": "escalate_noop",
                }],
            }

        escalated_groups: list[str] = output.get("escalated_tool_groups", [])
        current_groups: list[str] = list(state.get("allowed_tool_groups") or [])

        # Merge — preserve order, add new groups at end
        new_groups = list(dict.fromkeys(current_groups + escalated_groups))

        logger.info(
            "Escalate: expanding allowed_tool_groups from %s to %s",
            current_groups, new_groups,
        )

        return {
            "allowed_tool_groups": new_groups,
            "progress_decision": progress_decision_dict(
                status="continue",
                reason_summary=(
                    f"Escalated: added tool group '{output.get('group')}' — "
                    f"{output.get('reason', 'no reason given')}"
                ),
                next_instruction=f"Tool group '{output.get('group')}' is now available. Use it.",
            ),
            "trace_events": [{
                "type": "agent.progress.escalate",
                "status": "continue",
                "escalated_group": output.get("group"),
                "reason": output.get("reason"),
                "new_allowed_tool_groups": new_groups,
            }],
        }

    return None


def check_sql_repair_fastpath(state: DBFoxAgentState) -> dict[str, Any] | None:
    """Rule-based repair routing — coding-agent style before LLM judge."""
    from engine.agent.repair.sql_repair import (
        build_repair_trace_event,
        plan_sql_repair,
        repair_plan_to_progress_decision,
    )

    plan = plan_sql_repair(state)
    if plan is None:
        return None

    attempt = int(state.get("revision_count") or 0) + 1
    repair_trace = build_repair_trace_event(plan, attempt)
    decision_dump = repair_plan_to_progress_decision(plan)

    progress_trace: dict[str, Any] = {
        "type": "agent.progress.judged",
        "status": "continue",
        "failure_layer": plan.failure_layer,
        "root_cause": plan.root_cause,
        "recovery_strategy": plan.recovery_strategy,
        "user_visible_update": plan.user_visible_update,
        "fastpath": True,
        "error_class": plan.error_class,
    }

    return {
        "progress_decision": decision_dump,
        "repair_trace": [repair_trace],
        "trace_events": [repair_trace, progress_trace],
    }


def check_loop_prevention(state: DBFoxAgentState) -> dict[str, Any] | None:
    history = state.get("tool_call_history") or []
    if len(history) < 2:
        return None

    # Get the last tool execution
    current = history[-1]
    name = current.get("name")
    inputs = current.get("input") or {}
    curr_sig = _arg_signature(name, inputs)

    # Hash-based dedup: look for same tool + same canonical arg signature
    prev = None
    for item in reversed(history[:-1]):
        if item.get("name") != name:
            continue
        item_inputs = item.get("input") or {}
        if _arg_signature(name, item_inputs) == curr_sig:
            prev = item
            break

    # Also check exhausted_paths for pre-existing empty/failed signatures
    exhausted = set(state.get("exhausted_paths") or [])
    if not prev:
        for ep in exhausted:
            if ep.startswith(f"{name}::") and curr_sig in ep:
                logger.warning("Loop prevention: %s already exhausted — stopping", name)
                decision = progress_decision_dict(
                    status="clarify",
                    reason_summary=f"{name} with these arguments was already exhausted in a previous step.",
                    should_finalize=True,
                    should_ask_user=True,
                )
                return {
                    "status": "waiting_user",
                    "progress_decision": decision,
                    "trace_events": [progress_trace(decision, fastpath=True)],
                }
        return None

    # Duplicate detected — hash match found.  Each rule below fires the circuit breaker.
    logger.warning("Loop prevention: %s repeated with same args (sig=%s)", name, curr_sig)

    # 1. same db.search empty result twice triggers stop / clarify.
    if name == "db.search":
        current_cnt = current.get("results_count")
        prev_cnt = prev.get("results_count")
        if current_cnt == 0 and prev_cnt == 0:
            decision = progress_decision_dict(
                status="clarify",
                reason_summary="The search for query matches returned no results twice. Clarification is required.",
                should_finalize=True,
                should_ask_user=True,
            )
            return {
                "status": "waiting_user",
                "progress_decision": decision,
                "trace_events": [progress_trace(decision, fastpath=True)],
            }
            
    # 2. same schema.describe_table not found twice triggers stop / clarify.
    if name == "schema.describe_table":
        current_cnt = current.get("columns_count")
        prev_cnt = prev.get("columns_count")
        current_failed = current.get("status") == "failed"
        prev_failed = prev.get("status") == "failed"
        if (current_cnt == 0 or current_failed) and (prev_cnt == 0 or prev_failed):
            decision = progress_decision_dict(
                status="clarify",
                reason_summary=f"Table description was not found twice for table: {inputs.get('table_name')}.",
                should_finalize=True,
                should_ask_user=True,
            )
            return {
                "status": "waiting_user",
                "progress_decision": decision,
                "trace_events": [progress_trace(decision, fastpath=True)],
            }
            
    # 3. same db.inspect object missing twice triggers stop / clarify.
    if name == "db.inspect":
        current_failed = current.get("status") == "failed"
        prev_failed = prev.get("status") == "failed"
        if current_failed and prev_failed:
            decision = progress_decision_dict(
                status="clarify",
                reason_summary=f"Table or column inspection failed twice for: {inputs}.",
                should_finalize=True,
                should_ask_user=True,
            )
            return {
                "status": "waiting_user",
                "progress_decision": decision,
                "trace_events": [progress_trace(decision, fastpath=True)],
            }

    # 4. same sql.validate hard blockers twice triggers stop.
    if name == "sql.validate":
        curr_blockers = [r for r in current.get("blocked_reasons") or [] if r != "requires_confirmation"]
        prev_blockers = [r for r in prev.get("blocked_reasons") or [] if r != "requires_confirmation"]
        if curr_blockers and prev_blockers and sorted(curr_blockers) == sorted(prev_blockers):
            decision = progress_decision_dict(
                status="failed",
                reason_summary=f"SQL validation blocked by same safety guardrails twice: {curr_blockers}.",
                should_finalize=True,
                root_cause=f"SQL blocked twice: {curr_blockers}",
            )
            return {
                "status": "failed",
                "error": f"SQL blocked twice by safety guardrails: {curr_blockers}",
                "progress_decision": decision,
                "trace_events": [progress_trace(decision, fastpath=True)],
            }
        # 4b. sql.validate succeeded twice with same SQL but no execute → nudge/fail
        curr_success = current.get("status") == "success" and current.get("can_execute")
        prev_success = prev.get("status") == "success" and prev.get("can_execute")
        if curr_success and prev_success:
            # Check if sql.execute_readonly was called between these two validates
            exec_between = any(
                h.get("name") == "sql.execute_readonly"
                for h in history[history.index(prev):]
            )
            if not exec_between:
                decision = progress_decision_dict(
                    status="failed",
                    reason_summary="SQL validated twice without execution. Call sql.execute_readonly with the validated SQL, not sql.validate again.",
                    should_finalize=True,
                    root_cause="sql.validate loop — agent re-validated instead of executing",
                )
                return {
                    "status": "failed",
                    "error": "SQL validated twice without executing. Use sql.execute_readonly, not sql.validate.",
                    "progress_decision": decision,
                    "trace_events": [progress_trace(decision, fastpath=True)],
                }

    # 5. same db.query / sql.execute_readonly error twice → stop.
    if name in ("db.query", "sql.execute_readonly"):
        curr_status = current.get("status")
        prev_status = prev.get("status")
        curr_err = current.get("error")
        prev_err = prev.get("error")
        if curr_status == "failed" and prev_status == "failed" and curr_err == prev_err:
            decision = progress_decision_dict(
                status="failed",
                reason_summary=f"SQL execution failed twice with the same error: {curr_err}.",
                should_finalize=True,
                root_cause=curr_err,
            )
            return {
                "status": "failed",
                "error": f"SQL execution failed twice with same error: {curr_err}",
                "progress_decision": decision,
                "trace_events": [progress_trace(decision, fastpath=True)],
            }

    # 6. same schema.list_tables_page empty page twice → stop.
    if name == "schema.list_tables_page":
        curr_empty = (current.get("results_count") or 0) == 0
        prev_empty = (prev.get("results_count") or 0) == 0
        if curr_empty and prev_empty:
            decision = progress_decision_dict(
                status="clarify",
                reason_summary="Pagination returned empty results twice. No more tables to browse.",
                should_finalize=True,
                should_ask_user=True,
            )
            return {
                "status": "waiting_user",
                "progress_decision": decision,
                "trace_events": [progress_trace(decision, fastpath=True)],
            }

    # 7. same schema.expand_related_tables empty twice → stop.
    if name == "schema.expand_related_tables":
        curr_empty = (current.get("results_count") or 0) == 0
        prev_empty = (prev.get("results_count") or 0) == 0
        if curr_empty and prev_empty:
            decision = progress_decision_dict(
                status="clarify",
                reason_summary=f"No FK relationships found twice for table: {inputs.get('table_name')}.",
                should_finalize=True,
                should_ask_user=True,
            )
            return {
                "status": "waiting_user",
                "progress_decision": decision,
                "trace_events": [progress_trace(decision, fastpath=True)],
            }

    # 8. Generic: same tool + same args + same failure twice → stop.
    curr_status = current.get("status")
    prev_status = prev.get("status")
    if curr_status == "failed" and prev_status == "failed":
        decision = progress_decision_dict(
            status="failed",
            reason_summary=f"Tool '{name}' failed twice with the same arguments.",
            should_finalize=True,
            root_cause=f"Repeated failure: {name}",
        )
        return {
            "status": "failed",
            "error": f"Tool '{name}' failed twice with same arguments.",
            "progress_decision": decision,
            "trace_events": [progress_trace(decision, fastpath=True)],
        }

    return None


def deterministic_progress_fastpath(state: DBFoxAgentState) -> dict[str, Any] | None:
    """Rule-based ReAct progress routing for the common path."""
    status = state.get("status", "running")
    error = state.get("error")
    step_count = int(state.get("step_count", 0))
    max_steps = int(state.get("max_steps", 50))

    # ---- Loop prevention checks --------------------
    loop_result = check_loop_prevention(state)
    if loop_result is not None:
        return loop_result

    if status == "failed" or error:
        reason = str(error or "Agent reported failure.")
        decision = progress_decision_dict(
            status="failed",
            reason_summary=reason,
            root_cause=reason,
            should_finalize=True,
        )
        return {
            "status": "failed",
            "error": reason,
            "progress_decision": decision,
            "trace_events": [progress_trace(decision, fastpath=True)],
        }

    if status == "completed":
        decision = progress_decision_dict(
            status="complete",
            reason_summary="Agent marked complete.",
            should_finalize=True,
        )
        return {
            "progress_decision": decision,
            "trace_events": [progress_trace(decision, fastpath=True)],
        }

    if status == "waiting_user":
        decision = progress_decision_dict(
            status="clarify",
            reason_summary="Agent is waiting for user input.",
            should_ask_user=True,
            should_finalize=True,
        )
        return {
            "progress_decision": decision,
            "trace_events": [progress_trace(decision, fastpath=True)],
        }

    answer = state.get("answer") or state.get("final_answer")
    if isinstance(answer, dict) and answer.get("answer"):
        decision = progress_decision_dict(
            status="complete",
            reason_summary="Answer payload exists.",
            should_finalize=True,
        )
        return {
            "progress_decision": decision,
            "trace_events": [progress_trace(decision, fastpath=True)],
        }

    # ---- Analysis hint: db.query succeeded but no analysis step yet --------
    # The answer.synthesize tool handles analysis and final answer in one step.
    # We only emit a gentle hint when the model appears stuck (cycling).
    execution = state.get("execution")
    if (isinstance(execution, dict) and execution.get("success")
            and not state.get("answer")
            and not state.get("final_answer")):
        # Only intervene if model has been cycling (called db.query multiple times
        # without producing text or calling answer.synthesize)
        last_tool_results = state.get("last_tool_results") or []
        query_call_count = sum(
            1 for r in last_tool_results
            if isinstance(r, dict) and r.get("name") == "db.query"
        )
        if query_call_count >= 2 and step_count > 4:
            decision = progress_decision_dict(
                status="continue",
                reason_summary="Multiple db.query calls without analysis or answer — consider calling answer.synthesize or answering the user.",
                next_action_hint="You have query results. Consider calling answer.synthesize for analysis, or answer the user directly if the results are simple.",
            )
            return {
                "progress_decision": decision,
                "trace_events": [progress_trace(decision, fastpath=True)],
            }

    messages = state.get("messages") or []
    if messages:
        last = messages[-1]
        if is_ai_message(last) and not message_tool_calls(last):
            content = message_content_text(last)
            if content:
                decision = progress_decision_dict(
                    status="complete",
                    reason_summary="Model produced a final text response.",
                    should_finalize=True,
                )
                return {
                    "progress_decision": decision,
                    "trace_events": [progress_trace(decision, fastpath=True)],
                }

    if step_count >= max_steps:
        reason = _max_steps_reason(state, max_steps)
        decision = progress_decision_dict(
            status="failed",
            reason_summary="Max steps reached without an answer.",
            root_cause=reason,
            should_finalize=True,
            completion_reason="max_steps_reached",
        )
        return {
            "status": "failed",
            "error": reason,
            "progress_decision": decision,
            "trace_events": [progress_trace(decision, fastpath=True)],
        }

    if state.get("last_tool_results"):
        decision = progress_decision_dict(
            status="continue",
            reason_summary="Tool observation received; continuing ReAct loop.",
            next_action_hint="Use the latest tool observation to decide the next step or final answer.",
        )
        return {
            "progress_decision": decision,
            "trace_events": [progress_trace(decision, fastpath=True)],
        }

    return None


def guess_failure_layer(error: str) -> str:
    """Heuristic to map error text to a failure layer for rule-based fallback."""
    el = error.lower()
    if any(k in el for k in ("column", "table", "schema", "unknown", "not found")):
        return "schema"
    if any(k in el for k in ("guardrail", "trust gate", "validation", "safety")):
        return "sql_validation"
    if any(k in el for k in ("timeout", "connection", "execute", "database")):
        return "execution"
    if any(k in el for k in ("policy", "blocked")):
        return "policy"
    return "unknown"


def progress_decision_dict(
    *,
    status: str,
    reason_summary: str = "",
    completion_reason: str | None = None,
    failure_layer: str | None = None,
    root_cause: str | None = None,
    recovery_strategy: str | None = None,
    should_retry: bool = False,
    retry_budget: int = 0,
    should_replan: bool = False,
    should_finalize: bool = False,
    revised_plan_hint: dict | None = None,
    should_ask_user: bool = False,
    clarification_question: str | None = None,
    next_action_hint: str | None = None,
    missing_evidence: list[str] | None = None,
    user_visible_update: str | None = None,
    next_instruction: str | None = None,
    next_tool_groups: list[str] | None = None,
    should_consult_memory: bool = False,
) -> dict[str, Any]:
    return {
        "status": status,
        "reason_summary": reason_summary,
        "completion_reason": completion_reason,
        "failure_layer": failure_layer,
        "root_cause": root_cause,
        "recovery_strategy": recovery_strategy,
        "should_retry": should_retry,
        "retry_budget": retry_budget,
        "should_replan": should_replan,
        "should_finalize": should_finalize,
        "revised_plan_hint": revised_plan_hint,
        "should_ask_user": should_ask_user,
        "clarification_question": clarification_question,
        "next_action_hint": next_action_hint,
        "missing_evidence": list(missing_evidence or []),
        "user_visible_update": user_visible_update,
        "next_instruction": next_instruction,
        "next_tool_groups": list(next_tool_groups or []),
        "should_consult_memory": should_consult_memory,
    }


def progress_trace(decision: dict[str, Any], *, fastpath: bool) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "type": "agent.progress.judged",
        "status": decision.get("status"),
        "should_replan": decision.get("should_replan", False),
        "should_finalize": decision.get("should_finalize", False),
        "should_retry": decision.get("should_retry", False),
        "retry_budget": decision.get("retry_budget", 0),
        "reason_summary": decision.get("reason_summary", ""),
        "fastpath": fastpath,
    }
    if decision.get("failure_layer"):
        trace["failure_layer"] = decision["failure_layer"]
    if decision.get("root_cause"):
        trace["root_cause"] = decision["root_cause"]
    if decision.get("recovery_strategy"):
        trace["recovery_strategy"] = decision["recovery_strategy"]
    if decision.get("next_action_hint"):
        trace["next_action_hint"] = decision["next_action_hint"]
    if decision.get("user_visible_update"):
        trace["user_visible_update"] = decision["user_visible_update"]
    return trace


def rule_fallback(state: DBFoxAgentState) -> dict[str, Any]:
    """Simple rule-based fallback when the Progress Judge LLM is unavailable."""
    status = state.get("status", "running")
    step_count = int(state.get("step_count", 0))
    max_steps = int(state.get("max_steps", 50))
    error = state.get("error")
    answer = state.get("answer") or state.get("final_answer")
    execution = state.get("execution")

    if error and status == "failed":
        decision = ProgressDecision(
            status="failed", reason_summary="Agent reported failure.",
            failure_layer=guess_failure_layer(error),
            root_cause=error,
            should_finalize=True,
        )
    elif status == "completed":
        decision = ProgressDecision(status="complete", reason_summary="Agent marked complete.")
    elif status == "waiting_user":
        decision = ProgressDecision(status="clarify", reason_summary="Agent is waiting for user input.")
    elif answer and answer.get("answer"):
        decision = ProgressDecision(status="complete", reason_summary="Agent produced an answer.")
    elif (isinstance(execution, dict) and execution.get("success")
            and not state.get("answer")):
        decision = ProgressDecision(
            status="continue",
            reason_summary="Query succeeded. You may call answer.synthesize for analysis, or answer directly.",
            next_action_hint="Consider calling answer.synthesize for analysis, or answer the user directly if the results are simple.",
        )
    elif step_count >= max_steps:
        max_steps_error = _max_steps_reason(state, max_steps)
        decision = ProgressDecision(
            status="failed", reason_summary="Max steps reached without an answer.",
            root_cause=max_steps_error,
            should_finalize=True,
            completion_reason="max_steps_reached",
        )
        return {
            "status": "failed",
            "error": error or max_steps_error,
            "progress_decision": decision.model_dump(mode="json"),
            "trace_events": [{
                "type": "agent.progress.judged",
                "status": decision.status,
                "should_finalize": True,
                "completion_reason": "max_steps_reached",
                "fallback": True,
            }],
        }
    else:
        decision = ProgressDecision(status="continue", reason_summary="Continuing ReAct loop.")

    return {
        "progress_decision": decision.model_dump(mode="json"),
        "trace_events": [{
            "type": "agent.progress.judged",
            "status": decision.status,
            "should_replan": decision.should_replan,
            "should_finalize": decision.should_finalize,
            "fallback": True,
        }],
    }
