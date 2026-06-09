from __future__ import annotations
from typing import Any
from engine.agent_kernel.state import KernelState
from engine.agent_kernel.plan_schema import AgentPlan, PlanStep
from engine.agent_kernel.tool_args import resolve_tool_args

def select_next_action(state: KernelState) -> dict[str, Any]:
    raw_plan = state.get("agent_plan")
    if not raw_plan:
        return {"status": "running", "needs_replan": True}
        
    plan = AgentPlan.model_validate(raw_plan)
    
    # Find the first pending step whose dependencies are completed
    next_step = None
    completed_ids = {s.id for s in plan.steps if s.status == "completed"}
    
    for step in plan.steps:
        if step.status == "pending":
            deps_met = all(dep in completed_ids for dep in step.depends_on)
            if deps_met:
                next_step = step
                break
                
    if not next_step:
        return {
            "status": "running",
            "pending_tool_call": None,
        }
        
    # Resolve arguments using step + state
    args = resolve_tool_args(next_step, state)
    
    # Update status to running
    next_step.status = "running"
    
    return {
        "status": "running",
        "current_step_id": next_step.id,
        "pending_tool_call": {
            "tool_name": next_step.tool_name,
            "args": args,
            "reason": next_step.purpose or f"Execute {next_step.tool_name}",
        },
        "agent_plan": plan.model_dump(mode="json"),
    }
