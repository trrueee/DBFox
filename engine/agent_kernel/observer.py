from __future__ import annotations
from typing import Any
from engine.agent_kernel.state import KernelState
from engine.agent_kernel.plan_schema import AgentPlan, PlanStep

def observe_agent_loop(state: KernelState) -> dict[str, Any]:
    raw_plan = state.get("agent_plan")
    current_step_id = state.get("current_step_id")
    
    update: dict[str, Any] = {}
    
    if raw_plan and current_step_id:
        plan = AgentPlan.model_validate(raw_plan)
        step = next((s for s in plan.steps if s.id == current_step_id), None)
        
        if step:
            # Check if there is a pending approval in state or waiting approval
            if state.get("status") == "waiting_approval" or state.get("pending_approval"):
                step.status = "waiting_approval"
            else:
                last_obs_raw = state.get("last_observation")
                if last_obs_raw and isinstance(last_obs_raw, dict):
                    obs_status = last_obs_raw.get("status")
                    if obs_status == "success":
                        step.status = "completed"
                        step.error = None
                    elif obs_status == "failed":
                        step.status = "failed"
                        step.error = last_obs_raw.get("error")
                        step.attempt_count += 1
                    elif obs_status == "skipped":
                        step.status = "completed"
                        step.error = None
                        
        update["agent_plan"] = plan.model_dump(mode="json")
        
    return update
