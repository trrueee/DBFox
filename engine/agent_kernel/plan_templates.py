from __future__ import annotations
import uuid
from typing import Any
from engine.agent_kernel.state import KernelState, latest_user_message
from engine.agent_kernel.intent_fallback import classify_intent_fallback
from engine.agent_kernel.reference_resolver import resolve_reference
from engine.agent_kernel.plan_schema import AgentPlan, PlanStep

# Legacy route table for backward compatibility
INTENT_ROUTES: dict[str, list[str]] = {
    "new_data_question": [
        "schema.build_context",
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


def build_default_plan(state: KernelState) -> AgentPlan:
    # 1. Determine intent
    intent_payload = state.get("agent_intent") if isinstance(state.get("agent_intent"), dict) else {}
    intent = str(intent_payload.get("intent") or classify_intent_fallback(state))
    goal = state.get("goal") or latest_user_message(state) or "Analyze request"
    
    # 2. Build steps based on intent
    steps = []
    
    if intent == "new_data_question":
        steps.append(PlanStep(id="step_schema", tool_name="schema.build_context", purpose="Build schema context", title="Build schema context"))
        steps.append(PlanStep(id="step_generate", tool_name="sql.generate", purpose="Generate SQL candidate", title="Generate SQL candidate", depends_on=["step_schema"]))
        steps.append(PlanStep(id="step_validate", tool_name="sql.validate", purpose="Validate SQL with TrustGate", title="Validate SQL with TrustGate", depends_on=["step_generate"]))
        
        execute = state.get("execute", True)
        exec_tool = "sql.execute_readonly" if execute else "sql.skip_execution"
        steps.append(PlanStep(id="step_execute", tool_name=exec_tool, purpose="Execute SQL", title="Execute SQL", depends_on=["step_validate"]))
        steps.append(PlanStep(id="step_profile", tool_name="result.profile", purpose="Profile execution results", title="Profile execution results", depends_on=["step_execute"]))
        steps.append(PlanStep(id="step_synthesize", tool_name="answer.synthesize", purpose="Synthesize final answer", title="Synthesize final answer", depends_on=["step_profile"]))
        
    elif intent == "followup_on_result":
        steps.append(PlanStep(id="step_load_context", tool_name="followup.load_context", purpose="Load follow-up context", title="Load follow-up context"))
        steps.append(PlanStep(id="step_profile", tool_name="result.profile", purpose="Profile execution results", title="Profile execution results", depends_on=["step_load_context"]))
        steps.append(PlanStep(id="step_synthesize", tool_name="answer.synthesize", purpose="Synthesize final answer", title="Synthesize final answer", depends_on=["step_profile"]))
        
    elif intent == "explain_sql":
        steps.append(PlanStep(id="step_explain", tool_name="workspace.explain_sql", purpose="Explain SQL", title="Explain SQL"))
        
    elif intent == "revise_sql":
        steps.append(PlanStep(id="step_revise", tool_name="sql.revise", purpose="Revise SQL", title="Revise SQL"))
        steps.append(PlanStep(id="step_validate", tool_name="sql.validate", purpose="Validate revised SQL", title="Validate revised SQL", depends_on=["step_revise"]))
        
        execute = state.get("execute", True)
        exec_tool = "sql.execute_readonly" if execute else "sql.skip_execution"
        steps.append(PlanStep(id="step_execute", tool_name=exec_tool, purpose="Execute revised SQL", title="Execute revised SQL", depends_on=["step_validate"]))
        steps.append(PlanStep(id="step_profile", tool_name="result.profile", purpose="Profile results", title="Profile results", depends_on=["step_execute"]))
        steps.append(PlanStep(id="step_synthesize", tool_name="answer.synthesize", purpose="Synthesize final answer", title="Synthesize final answer", depends_on=["step_profile"]))
        
    elif intent == "approval_help":
        steps.append(PlanStep(id="step_synthesize", tool_name="answer.synthesize", purpose="Explain pending approval status", title="Explain pending approval status"))
        
    elif intent == "chart_request":
        steps.append(PlanStep(id="step_chart", tool_name="chart.suggest", purpose="Suggest chart", title="Suggest chart"))
        steps.append(PlanStep(id="step_synthesize", tool_name="answer.synthesize", purpose="Synthesize answer", title="Synthesize answer", depends_on=["step_chart"]))
        
    elif intent == "clarification":
        pass
        
    else:
        steps.append(PlanStep(id="step_synthesize", tool_name="answer.synthesize", purpose="Synthesize answer"))
        
    plan = AgentPlan(
        id=f"plan_{uuid.uuid4().hex[:8]}",
        goal=goal,
        status="created",
        steps=steps
    )
    
    optimize_plan_with_state(plan, state)
    
    return plan


def optimize_plan_with_state(plan: AgentPlan, state: KernelState) -> None:
    # Mark steps completed if state already contains their output.
    for step in plan.steps:
        if step.tool_name == "schema.build_context" and state.get("schema_context"):
            step.status = "completed"
        elif step.tool_name == "query_plan.build" and state.get("query_plan"):
            step.status = "completed"
        elif step.tool_name == "sql.generate" and state.get("sql"):
            step.status = "completed"
        elif step.tool_name == "sql.validate" and state.get("safety"):
            step.status = "completed"
        elif step.tool_name in ("sql.execute_readonly", "sql.skip_execution") and state.get("execution"):
            step.status = "completed"
        elif step.tool_name == "result.profile" and state.get("result_profile"):
            step.status = "completed"
        elif step.tool_name == "chart.suggest" and state.get("chart_suggestion"):
            step.status = "completed"
        elif step.tool_name == "followup.load_context" and state.get("followup_context"):
            step.status = "completed"
