from __future__ import annotations

from typing import Any, Optional

from engine.agent_kernel.intent_classifier import classify_intent_ai_first
from engine.agent_kernel.intent_fallback import classify_intent_fallback, classify_intent, AgentIntent
from engine.agent_kernel.reference_resolver import resolve_context, resolve_reference, _preview
from engine.agent_kernel.critics import critique_sql, critique_answer, corrected_answer
from engine.agent_kernel.plan_templates import plan_route
from engine.agent_kernel.state import KernelState, latest_user_message


try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any


def understand_node(state: KernelState, config: Optional[RunnableConfig] = None) -> dict[str, Any]:
    """Understand: classify the user's current intent before tool routing."""
    configurable = config.get("configurable", {}) if config else {}
    api_key = configurable.get("api_key")
    api_base = configurable.get("api_base")
    model_name = configurable.get("model_name")

    intent, source, llm_trace = classify_intent_ai_first(
        state,
        fallback=classify_intent_fallback,
        api_key=api_key,
        api_base=api_base,
        model_name=model_name,
    )
    reference = resolve_reference(state)
    payload = {
        "intent": intent,
        "confidence": _intent_confidence(intent, state, reference),
        "reason": _intent_reason(intent),
        "needs_execution": _intent_needs_execution(intent, state),
        "source": source,
        "reference": reference,
    }
    if llm_trace:
        payload["llm_trace"] = llm_trace
    return {
        "status": "running",
        "agent_intent": payload,
        "trace_events": [{"type": "agent.understand", "payload": payload}],
    }


def context_node(state: KernelState) -> dict[str, Any]:
    """Context: summarize reusable workspace/run/artifact context for routing."""
    context = resolve_context(state)
    return {
        "agent_context": context,
        "trace_events": [{"type": "agent.context", "payload": context}],
    }


def plan_node(state: KernelState) -> dict[str, Any]:
    """Plan: create a visible, executable route skeleton for the controller."""
    route = plan_route(state)
    return {
        "agent_lifecycle_plan": route,
        "trace_events": [{"type": "agent.plan", "payload": route}],
    }


def reflect_node(state: KernelState) -> dict[str, Any]:
    """Reflect: decide whether the loop should continue, revise, ask, or answer."""
    reflection = reflect(state)
    update: dict[str, Any] = {
        "agent_reflection": reflection,
        "trace_events": [{"type": "agent.reflect", "payload": reflection}],
    }
    critique = reflection.get("sql_critique") if isinstance(reflection, dict) else None
    if isinstance(critique, dict):
        update["agent_sql_critique"] = critique
        update["trace_events"].append({"type": "agent.sql_critic", "payload": critique})
    return update


def answer_node(state: KernelState) -> dict[str, Any]:
    """Answer: mark and guard the final answer before the graph ends."""
    answer = state.get("answer") or state.get("final_answer") or {}
    critique = critique_answer(state)
    effective_answer = corrected_answer(answer, critique) if critique.get("needs_correction") else answer
    payload = {
        "has_answer": bool(effective_answer),
        "answer_preview": _preview((effective_answer or {}).get("answer") if isinstance(effective_answer, dict) else effective_answer),
        "has_execution": bool(state.get("execution")),
        "has_sql": bool(state.get("sql")),
        "artifact_count": len(state.get("artifacts", [])),
        "reference": resolve_reference(state),
        "answer_critique": critique,
    }
    update: dict[str, Any] = {
        "trace_events": [
            {"type": "agent.answer_critic", "payload": critique},
            {"type": "agent.answer", "payload": payload},
        ],
    }
    if critique.get("needs_correction") and isinstance(effective_answer, dict):
        update["answer"] = effective_answer
        update["final_answer"] = effective_answer
    return update


def reflect(state: KernelState) -> dict[str, Any]:
    """Diagnostic reflection. Actual route transitions are controlled by graph_standalone conditional edges."""
    observation = state.get("last_observation") if isinstance(state.get("last_observation"), dict) else {}
    safety = state.get("safety") if isinstance(state.get("safety"), dict) else {}
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    answer = state.get("answer") if isinstance(state.get("answer"), dict) else {}
    reference = resolve_reference(state)
    critique = critique_sql(state)

    return {
        "last_tool_name": state.get("last_tool_name"),
        "has_answer": bool(answer),
        "has_execution": bool(execution),
        "has_error": bool(state.get("error")),
        "has_safety": bool(safety),
        "safety_blocked": bool(safety and not safety.get("can_execute")),
        "safety_requires_confirmation": bool(safety.get("requires_confirmation")),
        "revision_attempted": bool(state.get("revision_attempted")),
        "reference": reference,
        "sql_critique": critique,
        "last_observation_status": observation.get("status") if isinstance(observation, dict) else None,
    }


def _intent_needs_execution(intent: AgentIntent, state: KernelState) -> bool:
    if not state.get("execute", True):
        return False
    return intent in {"new_data_question", "followup_on_result", "chart_request"}


def _intent_confidence(intent: AgentIntent, state: KernelState, reference: dict[str, Any] | None = None) -> str:
    text = latest_user_message(state).strip()
    reference = reference or {}
    if not text:
        return "low"
    if reference.get("kind") and intent != "new_data_question":
        return "high"
    if intent == "new_data_question":
        return "medium"
    return "high"


def _intent_reason(intent: AgentIntent) -> str:
    return {
        "new_data_question": "Treat the message as a new data question unless existing context clearly changes the route.",
        "followup_on_result": "The user appears to ask about an existing result or prior analysis.",
        "explain_sql": "The user appears to ask for explanation of existing SQL rather than new execution.",
        "revise_sql": "The user appears to request a SQL modification.",
        "approval_help": "The user appears to ask about a pending approval or safety decision.",
        "chart_request": "The user appears to request visualization from existing SQL/result context.",
        "clarification": "The user appears to need clarification before tool execution.",
    }[intent]
