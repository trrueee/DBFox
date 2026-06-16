from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from engine.agent_core.tool_contract import get_contract
from engine.agent_core.types import ToolObservation

_ToolApplyFn = Callable[[dict[str, Any], dict[str, Any], ToolObservation], dict[str, Any]]


# ---------------------------------------------------------------------------
# State reset namespaces
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# State appliers
# ---------------------------------------------------------------------------


def _apply_environment_get_profile(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    result: dict[str, Any] = {"environment_profile": output}
    db_map = output.get("database_map")
    if db_map is not None:
        result["database_map"] = db_map
    return result


def _apply_semantic_resolve(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {"semantic_resolution": output}


def _apply_schema_list_tables(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {}


def _apply_schema_describe_table(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {}


def _apply_schema_refresh_catalog(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {}


def _apply_memory_search(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {}


def _apply_memory_write(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {}


def _apply_db_observe(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {"database_map": output}


def _apply_db_search(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {"db_search_results": output}


def _apply_db_inspect(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {"db_inspection": output}


def _apply_db_preview(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {"db_preview": output}


def _apply_db_query(state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    execution = dict(output)
    execution["success"] = output.get("status") == "success"
    execution["rowCount"] = output.get("rowCount", output.get("returned_rows", 0))
    execution["latencyMs"] = output.get("latencyMs", output.get("execution_time_ms", 0))
    update: dict[str, Any] = {"execution": execution}
    if output.get("safe_sql"):
        update["sql"] = output.get("safe_sql")
    return update


def _apply_result_profile(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {"result_profile": output}


def _apply_chart_suggest(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {"chart_suggestion": output}


def _apply_answer_synthesize(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {"answer": output, "final_answer": output}


def _apply_workspace_prefix(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    suggestions = output.get("suggestions") if isinstance(output.get("suggestions"), list) else []
    evidence: list[dict[str, Any]] = []
    if suggestions or output.get("proposed_sql"):
        evidence.append({
            "artifact_id": "sql_suggestion",
            "label": "SQL suggestion",
            "value": suggestions[0].get("title") if suggestions and isinstance(suggestions[0], dict) else "workspace suggestion",
        })
    answer = {
        "answer": str(output.get("answer") or ""),
        "key_findings": [],
        "evidence": evidence,
        "caveats": [],
        "recommendations": [],
        "follow_up_questions": [],
    }
    return {
        "answer": answer,
        "final_answer": answer,
        "status": "completed",
    }


TOOL_STATE_APPLIERS: dict[str, _ToolApplyFn] = {
    "environment.get_profile": _apply_environment_get_profile,
    "semantic.resolve": _apply_semantic_resolve,
    "schema.list_tables": _apply_schema_list_tables,
    "schema.describe_table": _apply_schema_describe_table,
    "schema.refresh_catalog": _apply_schema_refresh_catalog,
    "memory.search": _apply_memory_search,
    "memory.write": _apply_memory_write,
    "db.observe": _apply_db_observe,
    "db.search": _apply_db_search,
    "db.inspect": _apply_db_inspect,
    "db.preview": _apply_db_preview,
    "db.query": _apply_db_query,
    "result.profile": _apply_result_profile,
    "chart.suggest": _apply_chart_suggest,
    "answer.synthesize": _apply_answer_synthesize,
}

_ARTIFACT_TOOLS: frozenset[str] = frozenset({
    "db.preview",
    "db.query",
    "result.profile",
    "chart.suggest",
    "answer.synthesize",
})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_tool_result_to_state(
    *,
    state: dict[str, Any],
    tool_name: str,
    observation: ToolObservation,
) -> dict[str, Any]:
    contract = get_contract(tool_name)
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
                    "_merge_strategy": contract.merge_strategy,
                },
            }
        ],
    }

    # ── Failed path ──
    if observation.status == "failed":
        _apply_failed_telemetry(state, tool_name, observation, output, update)
        return update

    # ── Success path: contract-driven cleanup first ──
    for key in contract.on_success_clear:
        update[key] = None
    for key in contract.on_success_reset:
        update[key] = None

    # ── Then tool-specific state handler ──
    handler = TOOL_STATE_APPLIERS.get(tool_name)
    if handler is not None:
        tool_update = handler(state, output, observation)
    elif tool_name.startswith("workspace."):
        tool_update = _apply_workspace_prefix(state, output, observation)
    else:
        tool_update = {}

    extra_trace = tool_update.pop("_trace", None)
    if isinstance(extra_trace, list):
        update["trace_events"].extend(extra_trace)
    update.update(tool_update)

    # ── Artifact emission ──
    if contract.emit_artifact:
        update["artifacts"] = [_artifact_event(tool_name, output)]

    return update


def _apply_failed_telemetry(
    state: dict[str, Any],
    tool_name: str,
    observation: ToolObservation,
    output: dict[str, Any],
    update: dict[str, Any],
) -> None:
    telemetry = dict(output) if isinstance(output, dict) else {}
    failed_tool_call = state.get("pending_tool_call") if isinstance(state.get("pending_tool_call"), dict) else {"tool_name": tool_name, "args": {}}
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


# ---------------------------------------------------------------------------
# State merging (for streaming event view)
# ---------------------------------------------------------------------------

ADDITIVE_STATE_KEYS: frozenset[str] = frozenset({
    "plan_events",
    "tool_results",
    "artifacts",
    "trace_events",
})

MESSAGE_STATE_KEY: str = "messages"


def merge_state(state: dict[str, Any], update: dict[str, Any]) -> None:
    """Accumulate node updates into a streaming event view (NOT source of truth)."""
    for key, value in update.items():
        if key == MESSAGE_STATE_KEY:
            from langgraph.graph.message import add_messages
            current = state.get(key, [])
            state[key] = add_messages(current, value)
        elif key in ADDITIVE_STATE_KEYS:
            current = state.setdefault(key, [])
            if isinstance(current, list) and isinstance(value, list):
                current.extend(value)
            else:
                state[key] = value
        else:
            state[key] = value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _artifact_event(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"artifact_{uuid4().hex}",
        "tool_name": tool_name,
        "payload": payload,
    }
