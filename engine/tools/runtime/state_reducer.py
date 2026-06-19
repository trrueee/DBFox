from __future__ import annotations

from typing import Any
from uuid import uuid4

from engine.agent_core.types import ToolObservation

RESET_SELF_HEALING: dict[str, Any] = {
    "last_error_telemetry": None,
    "last_failed_tool_call": None,
}

RESET_ALL_ERROR_STATE = ("error", "last_error_telemetry", "last_failed_tool_call")
ERROR_CLEARING_TOOLS = {"db.query", "db.preview", "db.inspect"}
ARTIFACT_TOOLS = {"db.preview", "db.query", "result.profile", "chart.suggest", "answer.synthesize"}


def apply_tool_observation_to_state(
    *,
    state: dict[str, Any],
    tool_name: str,
    observation: ToolObservation,
    merge_strategy: str = "reuse",
) -> dict[str, Any]:
    output = observation.output or {}
    update: dict[str, Any] = {
        "tool_results": [observation.model_dump(mode="json")],
        "trace_events": [
            {
                "type": "tool.completed",
                "payload": {
                    "tool_name": tool_name,
                    "observation_name": observation.name,
                    "status": observation.status,
                    "_merge_strategy": merge_strategy,
                },
            }
        ],
    }

    if observation.status == "failed":
        _apply_failed_telemetry(state, tool_name, observation, output, update)
        return update

    if tool_name in ERROR_CLEARING_TOOLS:
        for key in RESET_ALL_ERROR_STATE:
            update[key] = None

    tool_update = _apply_success_output(tool_name, output)
    update.update(tool_update)

    if tool_name in ARTIFACT_TOOLS:
        update["artifacts"] = [_artifact_event(tool_name, output)]

    return update


def _apply_success_output(tool_name: str, output: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "environment.get_profile":
        result: dict[str, Any] = {"environment_profile": output}
        if output.get("database_map") is not None:
            result["database_map"] = output.get("database_map")
        return result
    if tool_name == "db.observe":
        return {"database_map": output}
    if tool_name == "db.search":
        return {"db_search_results": output}
    if tool_name == "db.inspect":
        return {"db_inspection": output}
    if tool_name == "db.preview":
        return {"db_preview": output}
    if tool_name == "db.query":
        execution = dict(output)
        execution["success"] = output.get("status") == "success"
        execution["rowCount"] = output.get("rowCount", output.get("returned_rows", 0))
        execution["latencyMs"] = output.get("latencyMs", output.get("execution_time_ms", 0))
        result = {"execution": execution, **RESET_SELF_HEALING}
        if output.get("safe_sql"):
            result["sql"] = output.get("safe_sql")
        return result
    if tool_name == "result.profile":
        return {"result_profile": output}
    if tool_name == "chart.suggest":
        return {"chart_suggestion": output}
    if tool_name == "answer.synthesize":
        return {"answer": output, "final_answer": output}
    return {}


def _apply_failed_telemetry(
    state: dict[str, Any],
    tool_name: str,
    observation: ToolObservation,
    output: dict[str, Any],
    update: dict[str, Any],
) -> None:
    telemetry = dict(output) if isinstance(output, dict) else {}
    failed_tool_call = (
        state.get("pending_tool_call")
        if isinstance(state.get("pending_tool_call"), dict)
        else {"tool_name": tool_name, "args": {}}
    )
    update["last_failed_tool_call"] = dict(failed_tool_call)
    update["last_error_telemetry"] = telemetry or {
        "error_type": "ToolExecutionError",
        "tool_name": tool_name,
        "step_name": observation.name,
        "retryable": False,
    }
    update["trace_events"].append({
        "type": "tool.failed.telemetry",
        "payload": {
            "tool_name": tool_name,
            "error_type": update["last_error_telemetry"].get("error_type"),
            "retryable": bool(update["last_error_telemetry"].get("retryable")),
        },
    })
    if tool_name == "db.query":
        update["execution"] = {
            "success": False,
            "error": observation.error,
            "error_telemetry": update["last_error_telemetry"],
        }
    if not bool(update["last_error_telemetry"].get("retryable")):
        update["error"] = observation.error or f"{tool_name} failed."
    else:
        update["error"] = None

def _artifact_event(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"artifact_{uuid4().hex}",
        "tool_name": tool_name,
        "payload": payload,
    }
