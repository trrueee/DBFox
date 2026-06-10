from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from engine.agent.planning.schemas import AgentPlanDirective
from engine.agent.planning.prompts import PLANNER_SYSTEM_PROMPT
from engine.agent.skills.registry import get_skill_registry
from engine.agent.skills.renderer import render_skill_list_for_planner
from engine.llm import get_chat_model
from engine.agent.graph.state import DataBoxAgentState
from engine.agent.graph.context import graph_context

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
    ctx = graph_context(config)
    model_name = ctx.model_name
    api_key = ctx.api_key
    api_base = ctx.api_base

    # Check whether we can actually call an LLM
    if not ctx.has_llm_credentials:
        logger.warning("No LLM credentials available — Planner falling back to permissive plan.")
        return _permissive_fallback(replan_count=int(state.get("replan_count", 0)))

    replan_count = int(state.get("replan_count", 0))
    # Detect actual replan from progress_decision status, not from counter
    progress = state.get("progress_decision") or {}
    is_replan = progress.get("status") == "replan"
    next_replan_count = replan_count + 1 if is_replan else replan_count

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
        failure_layer = prev_progress.get("failure_layer")
        root_cause = prev_progress.get("root_cause")
        recovery = prev_progress.get("recovery_strategy")
        next_groups = prev_progress.get("next_tool_groups", [])

        parts = [
            "## REPLAN REQUIRED",
            f"Previous plan was insufficient. Reason: {reason}",
        ]
        if failure_layer:
            parts.append(f"Failure layer: {failure_layer}")
        if root_cause:
            parts.append(f"Root cause: {root_cause}")
        if recovery:
            parts.append(f"Recovery strategy: {recovery}")
        if next_groups:
            parts.append(f"Suggested tool groups for new plan: {', '.join(next_groups)}")
        if hint:
            parts.append(f"Revised plan hint:\n```json\n{hint}\n```")
        context_parts.append("\n".join(parts))

    # ---- Memory context (Agent v2) ------------------------------------------
    memory_context_text = ""
    try:
        from engine.agent.memory_bridge import search_memory_for_planner
        memory_context_text = search_memory_for_planner(
            question=user_text,
            datasource_id=str(state.get("datasource_id") or ""),
            user_id=state.get("user_id") or state.get("thread_id"),
            project_id=state.get("project_id"),
        )
        if memory_context_text:
            context_parts.append(memory_context_text)
    except Exception as exc:
        logger.warning("Failed to search memory for planner: %s", exc)

    # ---- Skill catalog (Agent v2) -------------------------------------------
    try:
        registry = get_skill_registry()
        skill_summaries = registry.summarize_for_planner()
        if skill_summaries:
            context_parts.append(
                "## Available Skills\n"
                + render_skill_list_for_planner(registry.list_all())
            )
    except Exception as exc:
        logger.warning("Failed to load skill catalog for planner: %s", exc)

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
                                 "execution", "result", "chart", "answer"],
            should_call_tools=True,
            should_execute_sql=False,
            needs_clarification=False,
            success_criteria=["User question is answered with grounded evidence."],
            risk_notes=["Planner LLM call failed — using permissive fallback."],
            reasoning_summary=f"Planner error: {exc}",
        )
        return _plan_result(fallback, replan_count, is_replan=False)

    # ---- Handle clarification -----------------------------------------------
    if directive.needs_clarification:
        return {
            "plan_directive": directive.model_dump(mode="json"),
            "execution_mode": directive.execution_mode,
            "allowed_tool_groups": [],
            "status": "waiting_user",
            "error": None,
            "messages": [AIMessage(
                content=directive.clarification_question
                or "Could you clarify what you'd like to do?"
            )],
            "answer": {"answer": directive.clarification_question or "Could you clarify what you'd like to do?",
                        "key_findings": [], "evidence": [], "caveats": [],
                        "recommendations": [], "follow_up_questions": []},
            "final_answer": {"answer": directive.clarification_question or "Could you clarify what you'd like to do?",
                              "key_findings": [], "evidence": [], "caveats": [],
                              "recommendations": [], "follow_up_questions": []},
            "trace_events": [{
                "type": "agent.planner.clarification",
                "question": directive.clarification_question,
            }],
        }

    return _plan_result(directive, next_replan_count, is_replan)


def _plan_result(directive: AgentPlanDirective, count: int, is_replan: bool = False) -> dict[str, Any]:
    """Build the state update dict from a plan directive."""
    return {
        "plan_directive": directive.model_dump(mode="json"),
        "execution_mode": directive.execution_mode,
        "allowed_tool_groups": directive.allowed_tool_groups,
        "selected_skill_ids": directive.selected_skill_ids,
        "replan_count": count,
        "trace_events": [{
            "type": "agent.planner.completed",
            "task_type": directive.task_type,
            "execution_mode": directive.execution_mode,
            "allowed_tool_groups": directive.allowed_tool_groups,
            "selected_skill_ids": directive.selected_skill_ids,
            "should_call_tools": directive.should_call_tools,
            "should_execute_sql": directive.should_execute_sql,
            "is_replan": is_replan,
        }],
    }


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
            "execution", "result", "chart", "answer",
        ],
        should_call_tools=True,
        should_execute_sql=False,
        needs_clarification=False,
        success_criteria=["User question is answered with grounded evidence."],
        risk_notes=["Planner LLM unavailable — using permissive tool scope."],
        reasoning_summary="No LLM credentials available.",
    )
    return _plan_result(directive, replan_count)
