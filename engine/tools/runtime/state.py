"""Rebuild model/tool working state from durable observations."""

from __future__ import annotations

from typing import Any


def project_tool_output(state: dict[str, Any], tool_name: str, output: dict[str, Any]) -> None:
    if tool_name == "environment.get_profile":
        state["environment_profile"] = output
        if output.get("database_map") is not None:
            state["database_map"] = output["database_map"]
    elif tool_name == "db.observe":
        state["database_map"] = output
    elif tool_name == "db.search":
        state["db_search_results"] = output
    elif tool_name == "db.inspect":
        state["db_inspection"] = output
    elif tool_name == "db.preview":
        state["db_preview"] = output
    elif tool_name == "sql.validate":
        safety = output.get("execution_safety_decision")
        if not isinstance(safety, dict):
            safety = {key: output.get(key) for key in (
                "can_execute", "requires_confirmation", "safe_sql", "original_sql",
                "risk_level", "blocked_reasons", "messages",
            )}
        state["safety"] = safety
        state["sql"] = output.get("safe_sql") or output.get("original_sql")
    elif tool_name == "sql.execute_readonly":
        execution = dict(output)
        execution["success"] = bool(output.get("success")) or output.get("status") == "success"
        execution["rowCount"] = output.get("rowCount", output.get("returned_rows", 0))
        state["execution"] = execution
        if output.get("safe_sql"):
            state["sql"] = output["safe_sql"]
    elif tool_name == "chart.suggest":
        state["chart_suggestion"] = output
    elif tool_name == "plan.update":
        state["analysis_plan"] = output
    elif tool_name == "escalate.tool_group" and output.get("escalated_tool_groups"):
        state["allowed_tool_groups"] = list(output["escalated_tool_groups"])
