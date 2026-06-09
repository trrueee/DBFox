from __future__ import annotations
from typing import Any
from engine.agent_kernel.state import KernelState
from engine.agent_kernel.plan_schema import AgentPlan, ReflectDecision
from engine.agent_kernel.graph_retry import _revision_count, MAX_SQL_REVISIONS
from engine.agent_kernel.critics import critique_sql

def decide_reflection(state: KernelState) -> dict[str, Any]:
    # 1. Check if we are waiting for human approval
    if state.get("status") == "waiting_approval" or state.get("pending_approval"):
        decision = ReflectDecision(
            decision="approval",
            reason="Step requires human approval before proceeding.",
        )
        return {
            "reflect_decision": decision.model_dump(mode="json"),
        }
        
    # 2. Check if SQL critique requires a revision (before validation/execution)
    if state.get("sql") and not state.get("safety"):
        critique = critique_sql(state)
        if critique and critique.get("needs_correction"):
            decision = ReflectDecision(
                decision="revise",
                reason=f"SQL critique requested revision: {critique.get('reason') or 'SQL error found'}",
            )
            return {
                "reflect_decision": decision.model_dump(mode="json"),
                "error": critique.get("reason"),
            }
            
    # 3. Check if there was an execution or tool error in state
    if state.get("error"):
        sql = state.get("sql")
        if sql and _revision_count(state) < MAX_SQL_REVISIONS:
            decision = ReflectDecision(
                decision="revise",
                reason=f"SQL execution failed with error: {state.get('error')}. Revision needed.",
            )
            return {
                "reflect_decision": decision.model_dump(mode="json"),
            }
        else:
            decision = ReflectDecision(
                decision="fail",
                reason=f"Execution failed: {state.get('error')}",
            )
            return {
                "reflect_decision": decision.model_dump(mode="json"),
            }
            
    # 4. Check plan steps status
    raw_plan = state.get("agent_plan")
    if not raw_plan:
        decision = ReflectDecision(
            decision="replan",
            reason="No plan exists. Generating initial plan.",
        )
        return {
            "reflect_decision": decision.model_dump(mode="json"),
            "needs_replan": True,
        }
        
    plan = AgentPlan.model_validate(raw_plan)
    
    # Check if any step failed
    failed_steps = [s for s in plan.steps if s.status == "failed"]
    if failed_steps:
        last_failed = failed_steps[-1]
        if last_failed.tool_name == "sql.validate" and _revision_count(state) < MAX_SQL_REVISIONS:
            decision = ReflectDecision(
                decision="revise",
                reason="SQL validation failed. Revision needed.",
            )
            return {
                "reflect_decision": decision.model_dump(mode="json"),
            }
        elif last_failed.attempt_count < last_failed.max_attempts:
            # Retry
            last_failed.status = "pending"
            decision = ReflectDecision(
                decision="retry",
                reason=f"Step {last_failed.id} failed, retrying.",
            )
            return {
                "reflect_decision": decision.model_dump(mode="json"),
                "agent_plan": plan.model_dump(mode="json"),
            }
        else:
            decision = ReflectDecision(
                decision="fail",
                reason=f"Step {last_failed.id} failed and cannot be recovered.",
            )
            return {
                "reflect_decision": decision.model_dump(mode="json"),
            }
            
    # 5. Check if answer is set
    if state.get("answer") or state.get("final_answer"):
        decision = ReflectDecision(
            decision="answer",
            reason="Final answer has been generated.",
        )
        return {
            "reflect_decision": decision.model_dump(mode="json"),
        }
        
    # 6. Check if all steps are completed
    all_completed = all(s.status == "completed" for s in plan.steps)
    if all_completed:
        decision = ReflectDecision(
            decision="answer",
            reason="All plan steps completed.",
        )
        return {
            "reflect_decision": decision.model_dump(mode="json"),
        }
        
    # 7. Default continue
    decision = ReflectDecision(
        decision="continue",
        reason="Proceeding with the next step in the plan.",
    )
    return {
        "reflect_decision": decision.model_dump(mode="json"),
    }
