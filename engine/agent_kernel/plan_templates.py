from __future__ import annotations

from typing import Any

from engine.agent_kernel.state import KernelState
from engine.agent_kernel.intent_fallback import classify_intent_fallback
from engine.agent_kernel.reference_resolver import resolve_reference

# This is a presentation plan skeleton, not the execution graph controller.
# Execution is controlled by graph_standalone.py and ToolSpec metadata.

INTENT_ROUTES: dict[str, list[str]] = {
    "new_data_question": [
        "schema.build_context",
        "query_plan.build",
        "sql.generate",
        "sql.critic",
        "sql.validate",
        "sql.execute_readonly|sql.skip_execution",
        "result.profile",
        "chart.suggest",
        "followup.suggest",
        "answer.synthesize",
    ],
    "followup_on_result": ["followup.load_context", "result.profile", "answer.synthesize"],
    "explain_sql": ["answer.synthesize"],
    "revise_sql": ["sql.revise", "sql.validate", "answer.synthesize"],
    "approval_help": ["answer.synthesize"],
    "chart_request": ["chart.suggest", "answer.synthesize"],
    "clarification": ["ask_user|answer.synthesize"],
}


def plan_route(state: KernelState) -> dict[str, Any]:
    intent_payload = state.get("agent_intent") if isinstance(state.get("agent_intent"), dict) else {}
    intent = str(intent_payload.get("intent") or classify_intent_fallback(state))
    reference = intent_payload.get("reference") if isinstance(intent_payload.get("reference"), dict) else resolve_reference(state)
    steps = INTENT_ROUTES.get(intent, INTENT_ROUTES["new_data_question"])
    return {
        "intent": intent,
        "route": steps,
        "next_focus": _next_focus(state, steps, reference),
        "is_review_only": not bool(state.get("execute", True)),
        "reference": reference,
    }


def _next_focus(state: KernelState, steps: list[str], reference: dict[str, Any] | None = None) -> str:
    reference = reference or {}
    if reference.get("kind") == "approval" and "answer.synthesize" in steps:
        return "answer.synthesize"
    if reference.get("kind") == "sql" and "sql.revise" in steps and not state.get("safety"):
        return "sql.revise"
    if reference.get("kind") == "sql" and "answer.synthesize" in steps and "sql.revise" not in steps:
        return "answer.synthesize"
    if reference.get("kind") == "result" and "result.profile" in steps and not state.get("result_profile"):
        return "result.profile"
    if state.get("sql") and not state.get("agent_sql_critique") and "sql.critic" in steps:
        return "sql.critic"
    if not state.get("schema_context") and "schema.build_context" in steps:
        return "schema.build_context"
    if not state.get("query_plan") and "query_plan.build" in steps:
        return "query_plan.build"
    if not state.get("sql") and "sql.generate" in steps:
        return "sql.generate"
    if not state.get("safety") and "sql.validate" in steps:
        return "sql.validate"
    if not state.get("execution") and any(step.startswith("sql.execute") for step in steps):
        return "sql.execute_readonly"
    if not state.get("answer"):
        return "answer.synthesize"
    return "final_answer"
