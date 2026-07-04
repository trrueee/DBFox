from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from engine.agent_core.types import ToolObservation


def _fingerprint(sql: str) -> str:
    """Stable short hash of a SQL string for analysis unit keying."""
    return hashlib.sha256(sql.strip().encode()).hexdigest()[:16]


def _enrich_units(
    units: list[dict[str, Any]],
    unit_id: str,
    *,
    chart: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return a new list with the matching unit enriched in-place copy."""
    updated = list(units)
    for i, u in enumerate(updated):
        if u.get("id") == unit_id:
            copy = dict(u)
            if chart is not None:
                copy["chart"] = chart
            updated[i] = copy
            break
    return updated


TRACE_MAX_VALUE_LENGTH = 120  # chars per field value; rows array gets special caps
TRACE_MAX_ROWS = 3            # keep first 3 rows for trace UI preview


def _clip_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Return a trace-safe copy with long strings and large arrays trimmed."""
    if not isinstance(d, dict) or not d:
        return {}
    out: dict[str, Any] = {}
    for key, value in d.items():
        if isinstance(value, str):
            out[key] = value if len(value) <= TRACE_MAX_VALUE_LENGTH else value[:TRACE_MAX_VALUE_LENGTH - 3] + "..."
        elif isinstance(value, list):
            if key in ("rows", "results") and len(value) > TRACE_MAX_ROWS:
                clipped = list(value[:TRACE_MAX_ROWS])
                clipped.append(f"... ({len(value) - TRACE_MAX_ROWS} more items)")
                out[key] = clipped
            elif len(value) > 10:
                out[key] = list(value[:10])
            else:
                out[key] = list(value)
        elif isinstance(value, dict):
            out[key] = _clip_dict(value)
        else:
            out[key] = value
    return out


RESET_SELF_HEALING: dict[str, Any] = {
    "last_error_telemetry": None,
    "last_failed_tool_call": None,
}

RESET_ALL_ERROR_STATE = ("error", "last_error_telemetry", "last_failed_tool_call")
ERROR_CLEARING_TOOLS = {"db.preview", "db.inspect", "sql.execute_readonly"}
ARTIFACT_TOOLS = {"db.preview", "sql.execute_readonly", "chart.suggest"}


def apply_tool_observation_to_state(
    *,
    state: dict[str, Any],
    tool_name: str,
    observation: ToolObservation,
    merge_strategy: str = "reuse",
) -> dict[str, Any]:
    output = observation.output or {}
    # Truncate large outputs before writing to trace — keep under ~2KB for UI
    raw_input = observation.input or {}
    raw_output = observation.output or {}
    clipped_input = _clip_dict(raw_input)
    clipped_output = _clip_dict(raw_output)

    update: dict[str, Any] = {
        "tool_results": [observation.model_dump(mode="json")],
        "trace_events": [
            {
                "type": "agent.tool.completed",
                "payload": {
                    "tool_name": tool_name,
                    "observation_name": observation.name,
                    "status": observation.status,
                    "_merge_strategy": merge_strategy,
                    "input": clipped_input,
                    "output": clipped_output,
                    "latency_ms": observation.latency_ms,
                    "error": observation.error,
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

    # Enrich matching AnalysisUnit when chart.suggest runs
    if tool_name == "chart.suggest":
        unit_id = state.get("current_analysis_unit_id")
        if unit_id:
            update["analysis_units"] = _enrich_units(
                state.get("analysis_units", []), unit_id, chart=output,
            )

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
    if tool_name == "sql.execute_readonly":
        execution = dict(output)
        execution["success"] = bool(output.get("success")) or output.get("status") == "success"
        execution["rowCount"] = output.get("rowCount", output.get("returned_rows", 0))
        execution["latencyMs"] = output.get(
            "latencyMs",
            output.get("execution_time_ms", output.get("latency_ms", 0)),
        )
        result = {"execution": execution, **RESET_SELF_HEALING}
        if output.get("safe_sql"):
            result["sql"] = output.get("safe_sql")
        # Append AnalysisUnit for multi-query report composition
        if execution.get("success"):
            sql_text = output.get("safe_sql") or output.get("original_sql") or ""
            unit_id = _fingerprint(sql_text) if sql_text else uuid4().hex[:12]
            result["current_analysis_unit_id"] = unit_id
            result["analysis_units"] = [{
                "id": unit_id,
                "sql": sql_text,
                "execution": {
                    "columns": execution.get("columns", []),
                    "rows": execution.get("rows", []),
                    "rowCount": execution.get("rowCount", 0),
                    "latencyMs": execution.get("latencyMs", 0),
                },
                "is_empty": int(execution.get("rowCount", 0)) == 0,
                "is_truncated": bool(execution.get("truncated", False)),
            }]
        return result
    if tool_name == "sql.validate":
        safety = output.get("execution_safety_decision")
        if not isinstance(safety, dict):
            safety = {
                "can_execute": output.get("can_execute"),
                "requires_confirmation": output.get("requires_confirmation"),
                "safe_sql": output.get("safe_sql"),
                "original_sql": output.get("original_sql"),
                "risk_level": output.get("risk_level"),
                "blocked_reasons": output.get("blocked_reasons") or [],
                "messages": output.get("messages") or [],
            }
        result = {"safety": safety}
        sql = (
            output.get("safe_sql")
            or safety.get("safe_sql")
            or output.get("original_sql")
            or safety.get("original_sql")
        )
        if sql:
            result["sql"] = sql
        return result
    if tool_name == "chart.suggest":
        return {"chart_suggestion": output}
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
    if tool_name == "sql.execute_readonly":
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
