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
from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent.graph.message_utils import (
    first_user_text,
    message_content_text,
)

logger = logging.getLogger("dbfox.dbfox_agent.progress.llm_judge")


def call_llm_judge(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """LLM progress judge — evaluates execution context semantically to determine progress."""
    ctx = graph_context(config)
    model_name = ctx.model_name
    api_key = ctx.api_key
    api_base = ctx.api_base

    # ---- Build the judgment context -----------------------------------------
    context_parts = ["## Progress Judgment Request"]

    # User question
    messages = state.get("messages", [])
    user_text = first_user_text(messages)
    context_parts.append(f"### User Question\n{user_text}")

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
    max_steps = state.get("max_steps", 50)
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
        ], config)
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

    return {
        "progress_decision": decision_dump,
        "trace_events": [trace],
    }


def _compact_json(obj: Any) -> str:
    """Compact JSON serialization for context windows."""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
    except Exception:
        return str(obj)[:500]
