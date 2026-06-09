from __future__ import annotations

from collections.abc import Callable
from typing import Any, Hashable

from engine.agent_kernel.graph_retry import (
    _can_retry_transient,
    _error_telemetry,
    _is_sql_or_db_semantic_error,
    _revision_count,
)
from engine.agent_kernel.graph_shared import MAX_SQL_REVISIONS, _has_tool_call, _intent
from engine.agent_kernel.state import KernelState


TOOL_FALLBACK_ROUTE_MAP: dict[str, str | Callable[[KernelState], str]] = {
    "schema.build_context": "build_query_plan",
    "query_plan.build": "generate_sql",
    "sql.generate": "sql_critic",
    "sql.revise": "sql_critic",
    "sql.validate": "validation_route",
    "sql.execute_readonly": "execution_result_route",
    "sql.skip_execution": "execution_result_route",
    "result.profile": "chart_suggest",
    "chart.suggest": lambda state: "followup_suggest" if _intent(state) == "new_data_question" else "synthesize_answer",
    "followup.suggest": "synthesize_answer",
    "followup.load_context": "profile_result",
    "answer.synthesize": "answer",
}


def _observe_node(state: KernelState) -> dict[str, Any]:
    """Normalize latest tool result into agent_observation for routing and diagnostics."""
    observation = state.get("last_observation") if isinstance(state.get("last_observation"), dict) else {}
    telemetry = _error_telemetry(state)
    metadata = state.get("last_tool_metadata")
    next_route = metadata.get("next_route") if isinstance(metadata, dict) else None
    tool_name = state.get("last_tool_name")
    status = observation.get("status")
    error = observation.get("error")
    payload = {
        "tool_name": tool_name,
        "status": status,
        "success": status == "success",
        "has_error": bool(error),
        "retryable": bool(telemetry.get("retryable")),
        "semantic_error": _is_sql_or_db_semantic_error(state),
        "error_type": telemetry.get("error_type"),
        "next_route": next_route,
        "route_source": "tool_metadata" if next_route else "fallback_map",
    }
    return {"agent_observation": payload, "trace_events": [{"type": "agent.observe", "payload": payload}]}


def _after_observe(state: KernelState) -> str:
    obs = state.get("agent_observation") if isinstance(state.get("agent_observation"), dict) else {}

    retryable = obs.get("retryable") if "retryable" in obs else bool(_error_telemetry(state).get("retryable"))
    semantic_error = obs.get("semantic_error") if "semantic_error" in obs else _is_sql_or_db_semantic_error(state)
    has_error = obs.get("has_error") if "has_error" in obs else bool(state.get("error") or (state.get("last_error_telemetry") and True))

    if retryable:
        return "transient_retry" if _can_retry_transient(state) else "synthesize_answer"
    if semantic_error and has_error and state.get("sql") and _revision_count(state) < MAX_SQL_REVISIONS:
        return "revise_sql"
    if has_error and state.get("sql") and _revision_count(state) < MAX_SQL_REVISIONS:
        return "revise_sql"
    if has_error:
        return "synthesize_answer"

    next_route = obs.get("next_route")
    if isinstance(next_route, str) and next_route:
        if next_route == "followup_suggest" and _intent(state) != "new_data_question":
            return "synthesize_answer"
        return next_route
    metadata = state.get("last_tool_metadata")
    if isinstance(metadata, dict):
        next_route = metadata.get("next_route")
        if isinstance(next_route, str) and next_route:
            if next_route == "followup_suggest" and _intent(state) != "new_data_question":
                return "synthesize_answer"
            return next_route
    tool_name = str(state.get("last_tool_name") or "")
    if tool_name.startswith("workspace."):
        return "answer"
    route = TOOL_FALLBACK_ROUTE_MAP.get(tool_name)
    if isinstance(route, str):
        return route
    if callable(route):
        return route(state)
    return "synthesize_answer"


def _observe_routes() -> dict[Hashable, str]:
    return {
        "build_query_plan": "build_query_plan",
        "generate_sql": "generate_sql",
        "sql_critic": "sql_critic",
        "validation_route": "validation_route",
        "execution_result_route": "execution_result_route",
        "transient_retry": "transient_retry",
        "profile_result": "profile_result",
        "chart_suggest": "chart_suggest",
        "followup_suggest": "followup_suggest",
        "synthesize_answer": "synthesize_answer",
        "revise_sql": "revise_sql",
        "answer": "answer",
    }


def _after_sql_critic(state: KernelState) -> str:
    reflection = state.get("agent_reflection") if isinstance(state.get("agent_reflection"), dict) else {}
    critique = reflection.get("sql_critique") if isinstance(reflection.get("sql_critique"), dict) else state.get("agent_sql_critique")
    if isinstance(critique, dict) and critique.get("needs_revision"):
        return "revise_sql" if _revision_count(state) < MAX_SQL_REVISIONS else "synthesize_answer"
    return "validate_sql"
