from __future__ import annotations
from typing import Any
from engine.agent_kernel.state import KernelState
from engine.agent_kernel.plan_schema import AgentPlan, PlanStep
from engine.agent_kernel.plan_templates import build_default_plan

def plan_agent_loop(state: KernelState) -> dict[str, Any]:
    current_plan = state.get("agent_plan")
    needs_replan = state.get("needs_replan", False)
    
    reflect_raw = state.get("reflect_decision") or {}
    reflect_decision = reflect_raw.get("decision")
    
    if not current_plan:
        new_plan = build_default_plan(state)
        return {
            "agent_plan": new_plan.model_dump(mode="json"),
            "needs_replan": False,
        }
        
    plan = AgentPlan.model_validate(current_plan)
    
    if reflect_decision == "revise" or needs_replan:
        has_pending_revise = any(s.tool_name == "sql.revise" and s.status == "pending" for s in plan.steps)
        if not has_pending_revise:
            # Create a revise step
            revise_step = PlanStep(
                id=f"step_revise_{len(plan.steps)}",
                tool_name="sql.revise",
                purpose="Revise SQL based on critic/validation error",
                status="pending",
            )
            # Find the first step that is not completed, and insert revise_step before it
            insert_idx = 0
            for i, step in enumerate(plan.steps):
                if step.status != "completed":
                    insert_idx = i
                    break
            
            # Insert the revise step
            plan.steps.insert(insert_idx, revise_step)
            # The steps after revise_step will now depend on it
            for step in plan.steps[insert_idx+1:]:
                if "step_generate" in step.depends_on:
                    step.depends_on.append(revise_step.id)
                    
        return {
            "agent_plan": plan.model_dump(mode="json"),
            "needs_replan": False,
        }
        
    return {}
