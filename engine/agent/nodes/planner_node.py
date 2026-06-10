from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from engine.agent.planning.schemas import AgentPlanDirective
from engine.agent.planning.prompts import PLANNER_SYSTEM_PROMPT
from engine.agent.model.model_factory import get_chat_model
from engine.agent.graph.state import DataBoxAgentState

logger = logging.getLogger("databox.databox_agent.nodes.planner_node")


def create_plan(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """LLM Planner node — produces an AgentPlanDirective from the user message.

    Called at the start of every run and on replan (when the Progress Judge
    determines the current plan is insufficient).

    This is a SEMANTIC classifier, not a keyword router. It infers intent
    from meaning, context, and user goal.

    When no LLM credentials are available, falls back to a permissive plan
    that allows all safe tool groups (backward-compatible).
    """
    configurable = config.get("configurable") or {}
    model_name = configurable.get("model_name")
    api_key = configurable.get("api_key")
    api_base = configurable.get("api_base")

    # Check whether we can actually call an LLM
    if not _has_llm_credentials(api_key):
        logger.warning("No LLM credentials available — Planner falling back to permissive plan.")
        return _permissive_fallback(replan_count=int(state.get("replan_count", 0)))

    replan_count = int(state.get("replan_count", 0))
    is_replan = replan_count > 0

    # ---- Build the planner prompt -------------------------------------------
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

    workspace = state.get("workspace_context")
    follow_up = state.get("follow_up_context")

    context_parts = [f"## User Message\n{user_text}"]

    if workspace:
        context_parts.append(f"## Workspace Context\n```json\n{workspace}\n```")
    if follow_up:
        context_parts.append(f"## Follow-Up Context\n```json\n{follow_up}\n```")

    if is_replan:
        prev_progress = state.get("progress_decision") or {}
        hint = prev_progress.get("revised_plan_hint")
        reason = prev_progress.get("reason_summary", "Unknown reason")
        context_parts.append(
            f"## REPLAN REQUIRED\n"
            f"Previous plan was insufficient. Reason: {reason}\n"
        )
        if hint:
            context_parts.append(f"Revised plan hint:\n```json\n{hint}\n```")

    planner_prompt = "\n\n".join(context_parts)

    # ---- Call LLM with structured output ------------------------------------
    model = get_chat_model(
        model_name=model_name,
        api_key=api_key,
        api_base=api_base,
    )
    structured_model = model.with_structured_output(AgentPlanDirective)

    try:
        directive = structured_model.invoke([
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": planner_prompt},
        ])
    except Exception as exc:
        logger.error("Planner LLM call failed: %s", exc)
        # Fallback: allow all safe tool groups so the agent can still work
        fallback = AgentPlanDirective(
            task_type="ambiguous",
            grounding_level="none",
            execution_mode="suggest_only",
            allowed_tool_groups=["workspace", "schema", "semantic", "query_plan",
                                 "sql_generation", "sql_validation", "sql_repair",
                                 "result", "chart", "answer"],
            should_call_tools=True,
            should_execute_sql=False,
            needs_clarification=False,
            success_criteria=["User question is answered with grounded evidence."],
            risk_notes=["Planner LLM call failed — using permissive fallback."],
            reasoning_summary=f"Planner error: {exc}",
        )
        return _plan_result(fallback, replan_count)

    # ---- Handle clarification -----------------------------------------------
    if directive.needs_clarification:
        return {
            "plan_directive": directive.model_dump(mode="json"),
            "execution_mode": directive.execution_mode,
            "allowed_tool_groups": [],
            "status": "waiting_user",
            "error": None,
            "messages": [HumanMessage(
                content=directive.clarification_question
                or "Could you clarify what you'd like to do?"
            )],
            "trace_events": [{
                "type": "agent.planner.clarification",
                "question": directive.clarification_question,
            }],
        }

    return _plan_result(directive, replan_count)


def _plan_result(directive: AgentPlanDirective, replan_count: int) -> dict[str, Any]:
    """Build the state update dict from a plan directive."""
    return {
        "plan_directive": directive.model_dump(mode="json"),
        "execution_mode": directive.execution_mode,
        "allowed_tool_groups": directive.allowed_tool_groups,
        "replan_count": replan_count + 1 if replan_count > 0 else replan_count,
        "trace_events": [{
            "type": "agent.planner.completed",
            "task_type": directive.task_type,
            "execution_mode": directive.execution_mode,
            "allowed_tool_groups": directive.allowed_tool_groups,
            "should_call_tools": directive.should_call_tools,
            "should_execute_sql": directive.should_execute_sql,
            "is_replan": replan_count > 0,
        }],
    }


def _has_llm_credentials(api_key: str | None) -> bool:
    """Check whether we have credentials to call an LLM."""
    import os
    return bool((api_key or os.environ.get("OPENAI_API_KEY", "")).strip())


def _permissive_fallback(replan_count: int = 0) -> dict[str, Any]:
    """Return a permissive plan when the Planner LLM is unavailable.

    This preserves backward compatibility: the ReAct model still has access
    to all safe tool groups, and execution_mode is derived from the request.
    """
    directive = AgentPlanDirective(
        task_type="data_lookup",
        grounding_level="schema",
        execution_mode="user_requested_read",
        allowed_tool_groups=[
            "workspace", "schema", "semantic", "query_plan",
            "sql_generation", "sql_validation", "sql_repair",
            "result", "chart", "answer",
        ],
        should_call_tools=True,
        should_execute_sql=False,
        needs_clarification=False,
        success_criteria=["User question is answered with grounded evidence."],
        risk_notes=["Planner LLM unavailable — using permissive tool scope."],
        reasoning_summary="No LLM credentials available.",
    )
    return _plan_result(directive, replan_count)
