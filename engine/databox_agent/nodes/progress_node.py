from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from engine.databox_agent.progress.schemas import ProgressDecision
from engine.databox_agent.progress.prompts import PROGRESS_JUDGE_SYSTEM_PROMPT
from engine.databox_agent.model.model_factory import get_chat_model
from engine.databox_agent.graph.state import DataBoxAgentState

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

    When no LLM credentials are available, falls back to simple rule-based
    judgment (check step_count vs max_steps, check for error).
    """
    configurable = config.get("configurable") or {}
    model_name = configurable.get("model_name")
    api_key = configurable.get("api_key")
    api_base = configurable.get("api_base")

    if not _has_llm_credentials(api_key):
        return _rule_fallback(state)

    # ---- Build the judgment context -----------------------------------------
    context_parts = ["## Progress Judgment Request"]

    # User question
    messages = state.get("messages", [])
    user_text = ""
    if messages:
        first = messages[0]
        content = getattr(first, "content", "")
        if isinstance(content, str):
            user_text = content
        elif isinstance(content, list):
            parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            user_text = " ".join(parts).strip()
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
        last_content = getattr(last, "content", "")
        if isinstance(last_content, str) and last_content:
            context_parts.append(f"### Last Model Response\n{last_content[:600]}")
        elif isinstance(last_content, list):
            parts = [p.get("text", "") for p in last_content if isinstance(p, dict)]
            text = " ".join(parts).strip()
            if text:
                context_parts.append(f"### Last Model Response\n{text[:600]}")

    # Step count
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", 20)
    context_parts.append(f"### Progress\nstep_count={step_count}, max_steps={max_steps}")

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
    return {
        "progress_decision": decision.model_dump(mode="json"),
        "trace_events": [{
            "type": "agent.progress.judged",
            "status": decision.status,
            "should_replan": decision.should_replan,
            "should_finalize": decision.should_finalize,
        }],
    }


def _compact_json(obj: Any) -> str:
    """Compact JSON serialization for context windows."""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
    except Exception:
        return str(obj)[:500]


def _has_llm_credentials(api_key: str | None) -> bool:
    """Check whether we have credentials to call an LLM."""
    import os
    return bool((api_key or os.environ.get("OPENAI_API_KEY", "")).strip())


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
        decision = ProgressDecision(status="failed", reason_summary="Agent reported failure.")
    elif status == "completed":
        decision = ProgressDecision(status="complete", reason_summary="Agent marked complete.")
    elif status == "waiting_user":
        decision = ProgressDecision(status="clarify", reason_summary="Agent is waiting for user input.")
    elif answer and answer.get("answer"):
        decision = ProgressDecision(status="complete", reason_summary="Agent produced an answer.")
    elif step_count >= max_steps:
        decision = ProgressDecision(status="complete", reason_summary="Max steps reached — finalizing.")
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
