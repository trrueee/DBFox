from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from engine.agent.progress.schemas import ProgressDecision
from engine.agent.progress.prompts import PROGRESS_JUDGE_SYSTEM_PROMPT
from engine.agent.progress.clarification_policy import should_progress_clarify
from engine.agent.skills.registry import get_skill_registry
from engine.agent.skills.renderer import render_recovery_for_progress
from engine.llm import get_chat_model
from engine.agent.graph.state import DataBoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent.graph.message_utils import (
    first_user_text,
    is_ai_message,
    message_content_text,
    message_tool_calls,
)

logger = logging.getLogger("databox.databox_agent.nodes.progress_node")


def judge_progress(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """LLM Progress Judge — decides whether the task is complete after each observe.

    Called after every tool observation cycle and when the model produces
    no tool_calls. It semantically judges from the full execution trace whether:
    - The user's goal is satisfied (complete)
    - More work is needed (continue)
    - The plan was wrong (replan)
    - The user should be asked (clarify)
    - The task was blocked (blocked)
    - The task cannot be completed (failed)

    This is a SEMANTIC judge, not a rule checker.

    When no LLM credentials are available, the agent cannot run; this is
    enforced at the API layer. If this node is reached without credentials
    (defense-in-depth), raise immediately.
    """
    ctx = graph_context(config)
    model_name = ctx.model_name
    api_key = ctx.api_key
    api_base = ctx.api_base

    if not ctx.has_llm_credentials:
        raise RuntimeError("Progress judge requires LLM credentials.")

    # ---- Fast path: escalate.tool_group was called --------------------------
    escalate_result = _check_escalate(state)
    if escalate_result:
        return _enrich_progress_result(escalate_result, state)

    # ---- Fast path: SQL / schema repair without LLM judge -------------------
    repair_result = _check_sql_repair_fastpath(state)
    if repair_result:
        return _enrich_progress_result(repair_result, state)

    # ---- Fast path: standard ReAct progress routing -------------------------
    deterministic_result = _deterministic_progress_fastpath(state)
    if deterministic_result:
        return _enrich_progress_result(deterministic_result, state)

    # ---- Build the judgment context -----------------------------------------
    context_parts = ["## Progress Judgment Request"]

    # User question
    messages = state.get("messages", [])
    user_text = first_user_text(messages)
    context_parts.append(f"### User Question\n{user_text}")

    # Plan directive
    plan = state.get("plan_directive") or {}
    if plan:
        context_parts.append(f"### Plan Directive\n```json\n{_compact_json(plan)}\n```")

    # States relevant to progress
    schema_ctx = state.get("schema_context")
    if schema_ctx:
        tables = schema_ctx.get("selected_tables") if isinstance(schema_ctx, dict) else None
        if tables:
            context_parts.append(f"### Schema Context\nSelected tables: {', '.join(tables)}")

    sql = state.get("sql")
    if sql:
        context_parts.append(f"### Current SQL\n```sql\n{sql[:500]}\n```")

    safety = state.get("safety")
    if safety:
        context_parts.append(f"### SQL Safety\ncan_execute={safety.get('can_execute')}, "
                             f"requires_confirmation={safety.get('requires_confirmation')}, "
                             f"blocked_reasons={safety.get('blocked_reasons')}")

    execution = state.get("execution")
    if execution:
        success = execution.get("success")
        rows = execution.get("rowCount", 0)
        context_parts.append(f"### Execution\nsuccess={success}, rows={rows}")
        if not success:
            context_parts.append(f"  Error: {execution.get('error')}")

    result_profile = state.get("result_profile")
    if result_profile:
        facts = result_profile.get("notable_facts") or []
        anomalies = result_profile.get("anomalies") or []
        context_parts.append(f"### Result Profile\nrow_count={result_profile.get('row_count')}, "
                             f"notable_facts={facts[:3]}, anomalies={anomalies[:3]}")

    error = state.get("error")
    if error:
        context_parts.append(f"### Runtime Error\n{error}")

    # Tool results summary
    last_results = state.get("last_tool_results") or []
    if last_results:
        tool_summaries = []
        for r in last_results[-5:]:  # Last 5 tool results
            if isinstance(r, dict):
                tool_summaries.append({
                    "name": r.get("name", "?"),
                    "status": r.get("status", "?"),
                    "error": r.get("error"),
                })
        context_parts.append(f"### Latest Tool Results\n```json\n{_compact_json(tool_summaries)}\n```")

    # Blocked tool calls
    blocked = state.get("blocked_tool_calls") or []
    if blocked:
        context_parts.append(f"### Blocked Tool Calls\n{len(blocked)} call(s) blocked by policy.")

    # Last assistant message
    if len(messages) > 1:
        last = messages[-1]
        text = message_content_text(last)
        if text:
            context_parts.append(f"### Last Model Response\n{text[:600]}")

    # ContextPack summary (Agent v2)
    context_pack_raw = state.get("context_pack")
    if context_pack_raw and isinstance(context_pack_raw, dict):
        try:
            from engine.agent.context_pack import ContextPack, render_for_judge
            pack = ContextPack.model_validate(context_pack_raw)
            context_parts.append(f"### Context Summary\n{render_for_judge(pack)}")
        except Exception:
            pass

    # Step count
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", 20)
    context_parts.append(f"### Progress\nstep_count={step_count}, max_steps={max_steps}")

    # ---- Active skill recovery context (Agent v2) --------------------------
    skill_ids: list[str] = state.get("selected_skill_ids", []) or []
    if skill_ids:
        try:
            reg = get_skill_registry()
            recovery_blocks: list[str] = []
            for sid in skill_ids:
                skill = reg.get(sid)
                if skill:
                    block = render_recovery_for_progress(skill)
                    if block:
                        recovery_blocks.append(block)
            if recovery_blocks:
                context_parts.append("\n\n".join(recovery_blocks))
        except Exception as exc:
            logger.warning("Failed to load skill recovery context for progress judge: %s", exc)

    # ---- Past recovery experience (Agent v2 memory integration) ------------
    has_failure = bool(error or (execution and not execution.get("success")))
    if has_failure:
        try:
            from engine.agent.memory_bridge import search_memory_for_recovery
            failure_text = str(error or execution.get("error", ""))
            recovery_mem = search_memory_for_recovery(
                error=failure_text,
                failure_layer=(state.get("progress_decision") or {}).get("failure_layer"),
                datasource_id=str(state.get("datasource_id") or ""),
                user_id=state.get("user_id") or state.get("thread_id"),
                project_id=state.get("project_id"),
            )
            if recovery_mem:
                context_parts.append(recovery_mem)
        except Exception as exc:
            logger.warning("Failed to search memory for recovery: %s", exc)

    judge_prompt = "\n\n".join(context_parts)

    # ---- Call LLM with structured output ------------------------------------
    model = get_chat_model(
        model_name=model_name,
        api_key=api_key,
        api_base=api_base,
    )
    structured_model = model.with_structured_output(ProgressDecision)

    try:
        decision = structured_model.invoke([
            {"role": "system", "content": PROGRESS_JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": judge_prompt},
        ])
    except Exception as exc:
        logger.error("Progress Judge LLM call failed: %s", exc)
        # Fallback: check if we have an answer, then complete; else fail
        answer = state.get("answer") or state.get("final_answer")
        if answer and answer.get("answer"):
            decision = ProgressDecision(
                status="complete",
                reason_summary="Progress Judge LLM call failed, but answer exists — completing.",
            )
        elif int(state.get("step_count", 0)) >= int(state.get("max_steps", 20)):
            decision = ProgressDecision(
                status="complete",
                reason_summary="Progress Judge LLM call failed, max steps reached — finalizing.",
            )
        else:
            decision = ProgressDecision(
                status="continue",
                reason_summary=f"Progress Judge LLM call failed: {exc} — continuing.",
            )

    # ---- Build result -------------------------------------------------------
    trace: dict[str, Any] = {
        "type": "agent.progress.judged",
        "status": decision.status,
        "should_replan": decision.should_replan,
        "should_finalize": decision.should_finalize,
        "should_retry": decision.should_retry,
        "retry_budget": decision.retry_budget,
    }
    if decision.failure_layer:
        trace["failure_layer"] = decision.failure_layer
    if decision.root_cause:
        trace["root_cause"] = decision.root_cause
    if decision.recovery_strategy:
        trace["recovery_strategy"] = decision.recovery_strategy
    if decision.next_action_hint:
        trace["next_action_hint"] = decision.next_action_hint
    if decision.missing_evidence:
        trace["missing_evidence"] = decision.missing_evidence
    if decision.user_visible_update:
        trace["user_visible_update"] = decision.user_visible_update

    decision_dump = decision.model_dump(mode="json")

    # Apply clarification policy to LLM clarify decisions
    if not should_progress_clarify(
        failure_layer=decision.failure_layer,
        root_cause=decision.root_cause,
        progress_status=decision.status,
    ):
        decision_dump["status"] = "continue"
        decision_dump["should_ask_user"] = False
        decision_dump["clarification_question"] = None
        if not decision_dump.get("next_action_hint"):
            decision_dump["next_action_hint"] = (
                decision.recovery_strategy
                or "Explore schema and repair SQL before asking the user."
            )
        trace["status"] = "continue"
        trace["clarification_suppressed"] = True

    return _enrich_progress_result({
        "progress_decision": decision_dump,
        "trace_events": [trace],
    }, state)


def _deterministic_progress_fastpath(state: DataBoxAgentState) -> dict[str, Any] | None:
    """Rule-based ReAct progress routing for the common path.

    Open-source ReAct loops usually continue after tool observations and stop
    when the model returns text without tool calls. Reserve the LLM judge for
    ambiguous/stuck cases instead of calling it after every step.
    """

    status = state.get("status", "running")
    error = state.get("error")
    step_count = int(state.get("step_count", 0))
    max_steps = int(state.get("max_steps", 20))

    if status == "failed" or error:
        reason = str(error or "Agent reported failure.")
        decision = _progress_decision_dict(
            status="failed",
            reason_summary=reason,
            root_cause=reason,
            should_finalize=True,
        )
        return {
            "status": "failed",
            "error": reason,
            "progress_decision": decision,
            "trace_events": [_progress_trace(decision, fastpath=True)],
        }

    if status == "completed":
        decision = _progress_decision_dict(
            status="complete",
            reason_summary="Agent marked complete.",
            should_finalize=True,
        )
        return {
            "progress_decision": decision,
            "trace_events": [_progress_trace(decision, fastpath=True)],
        }

    if status == "waiting_user":
        decision = _progress_decision_dict(
            status="clarify",
            reason_summary="Agent is waiting for user input.",
            should_ask_user=True,
            should_finalize=True,
        )
        return {
            "progress_decision": decision,
            "trace_events": [_progress_trace(decision, fastpath=True)],
        }

    if step_count >= max_steps:
        reason = f"Agent exceeded max_steps ({max_steps})."
        if not state.get("safety"):
            reason = "Agent stopped before SQL validation because max_steps was reached."
        decision = _progress_decision_dict(
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
            "trace_events": [_progress_trace(decision, fastpath=True)],
        }

    answer = state.get("answer") or state.get("final_answer")
    if isinstance(answer, dict) and answer.get("answer"):
        decision = _progress_decision_dict(
            status="complete",
            reason_summary="Answer payload exists.",
            should_finalize=True,
        )
        return {
            "progress_decision": decision,
            "trace_events": [_progress_trace(decision, fastpath=True)],
        }

    messages = state.get("messages") or []
    if messages:
        last = messages[-1]
        if is_ai_message(last) and not message_tool_calls(last):
            content = message_content_text(last)
            if content:
                decision = _progress_decision_dict(
                    status="complete",
                    reason_summary="Model produced a final text response.",
                    should_finalize=True,
                )
                return {
                    "progress_decision": decision,
                    "trace_events": [_progress_trace(decision, fastpath=True)],
                }

    if state.get("last_tool_results"):
        decision = _progress_decision_dict(
            status="continue",
            reason_summary="Tool observation received; continuing ReAct loop.",
            next_action_hint="Use the latest tool observation to decide the next step or final answer.",
        )
        return {
            "progress_decision": decision,
            "trace_events": [_progress_trace(decision, fastpath=True)],
        }

    return None


def _progress_decision_dict(
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


def _progress_trace(decision: dict[str, Any], *, fastpath: bool) -> dict[str, Any]:
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


def _compact_json(obj: Any) -> str:
    """Compact JSON serialization for context windows."""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
    except Exception:
        return str(obj)[:500]


def _enrich_progress_result(result: dict[str, Any], state: DataBoxAgentState) -> dict[str, Any]:
    """Attach visible_plan (Task Lens) and bump revision_count on repair continue."""
    decision_raw = result.get("progress_decision") or {}
    if not isinstance(decision_raw, dict):
        return result

    plan = state.get("plan_directive") or {}
    user_text = first_user_text(state.get("messages", []))
    visible = {
        "goal": plan.get("reasoning_summary") or user_text[:120] or "Agent task",
        "current_focus": (
            decision_raw.get("user_visible_update")
            or decision_raw.get("next_action_hint")
            or decision_raw.get("reason_summary")
            or ""
        ),
        "next_likely": decision_raw.get("next_action_hint") or "",
        "missing_evidence": decision_raw.get("missing_evidence") or [],
    }
    result["visible_plan"] = visible

    recovery = decision_raw.get("recovery_strategy")
    next_groups = decision_raw.get("next_tool_groups") or []
    if decision_raw.get("status") == "continue" and (recovery or next_groups):
        if recovery:
            result["revision_count"] = int(state.get("revision_count") or 0) + 1
        if next_groups:
            current_groups = list(state.get("allowed_tool_groups") or [])
            merged = list(dict.fromkeys(current_groups + list(next_groups)))
            result["allowed_tool_groups"] = merged
            result["repair_mode"] = True

    return result


def _check_sql_repair_fastpath(state: DataBoxAgentState) -> dict[str, Any] | None:
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


def _guess_failure_layer(error: str) -> str:
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


def _check_escalate(state: DataBoxAgentState) -> dict[str, Any] | None:
    """Fast-path: detect escalate.tool_group and expand allowed_tool_groups.

    When the model calls escalate.tool_group, we immediately expand the
    tool scope and return continue — no LLM judge needed.  This avoids
    wasting a full ReAct loop on escalation.

    Returns None if no escalation was detected (normal flow continues).
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
            # Escalate was called but the group was already available.
            # Still return continue — the model should proceed with what it has.
            return {
                "progress_decision": ProgressDecision(
                    status="continue",
                    reason_summary="Escalate called but group already available — continuing.",
                ).model_dump(mode="json"),
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
            "progress_decision": ProgressDecision(
                status="continue",
                reason_summary=(
                    f"Escalated: added tool group '{output.get('group')}' — "
                    f"{output.get('reason', 'no reason given')}"
                ),
                next_instruction=f"Tool group '{output.get('group')}' is now available. Use it.",
            ).model_dump(mode="json"),
            "trace_events": [{
                "type": "agent.progress.escalate",
                "status": "continue",
                "escalated_group": output.get("group"),
                "reason": output.get("reason"),
                "new_allowed_tool_groups": new_groups,
            }],
        }

    return None


def _rule_fallback(state: DataBoxAgentState) -> dict[str, Any]:
    """Simple rule-based fallback when the Progress Judge LLM is unavailable.

    Mirrors the old route_observe_output logic but with basic semantic checks.
    """
    status = state.get("status", "running")
    step_count = int(state.get("step_count", 0))
    max_steps = int(state.get("max_steps", 20))
    error = state.get("error")
    answer = state.get("answer") or state.get("final_answer")

    if error and status == "failed":
        decision = ProgressDecision(
            status="failed", reason_summary="Agent reported failure.",
            failure_layer=_guess_failure_layer(error),
            root_cause=error,
            should_finalize=True,
        )
    elif status == "completed":
        decision = ProgressDecision(status="complete", reason_summary="Agent marked complete.")
    elif status == "waiting_user":
        decision = ProgressDecision(status="clarify", reason_summary="Agent is waiting for user input.")
    elif answer and answer.get("answer"):
        decision = ProgressDecision(status="complete", reason_summary="Agent produced an answer.")
    elif step_count >= max_steps:
        # No answer and the step budget is exhausted — this is a failure, not a
        # completion. Mirror model_node's hard-block error semantics.
        if not state.get("safety"):
            max_steps_error = "Agent stopped before SQL validation because max_steps was reached."
        else:
            max_steps_error = f"Agent exceeded max_steps ({max_steps})."
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
