from __future__ import annotations
from typing import Any
from engine.agent_kernel.state import KernelState, latest_user_message
from engine.agent_kernel.plan_schema import PlanStep

def resolve_tool_args(step: PlanStep, state: KernelState) -> dict[str, Any]:
    args = dict(step.args) if step.args else {}
    tool_name = step.tool_name
    
    if tool_name == "schema.build_context":
        if "question" not in args:
            args["question"] = latest_user_message(state)
            
    elif tool_name == "query_plan.build":
        pass
        
    elif tool_name == "sql.generate":
        pass
        
    elif tool_name == "sql.validate":
        if "sql" not in args:
            args["sql"] = state.get("sql")
            
    elif tool_name == "sql.execute_readonly":
        if "sql" not in args:
            safety = state.get("safety") or {}
            args["sql"] = safety.get("safe_sql") or state.get("sql")
            
    elif tool_name == "sql.revise":
        if "sql" not in args:
            args["sql"] = state.get("sql")
        if "instruction" not in args:
            args["instruction"] = latest_user_message(state)
        if "error" not in args:
            args["error"] = state.get("error")
            
    elif tool_name == "result.profile":
        pass
        
    elif tool_name == "chart.suggest":
        pass
        
    elif tool_name == "followup.suggest":
        pass
        
    elif tool_name == "answer.synthesize":
        pass
        
    elif tool_name.startswith("workspace."):
        if "question" not in args:
            args["question"] = latest_user_message(state)
            
    return args
