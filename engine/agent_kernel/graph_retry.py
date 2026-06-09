from __future__ import annotations

from typing import Any

from engine.agent_kernel.graph_shared import MAX_SQL_REVISIONS, MAX_TRANSIENT_RETRIES
from engine.agent_kernel.lifecycle import resolve_reference
from engine.agent_kernel.state import KernelState, latest_user_message


def _error_telemetry(state: KernelState) -> dict[str, Any]:
    telemetry = state.get("last_error_telemetry")
    return telemetry if isinstance(telemetry, dict) else {}


def _failed_tool_name(state: KernelState) -> str:
    failed_tool_call = state.get("last_failed_tool_call") if isinstance(state.get("last_failed_tool_call"), dict) else {}
    telemetry = _error_telemetry(state)
    return str(failed_tool_call.get("tool_name") or telemetry.get("tool_name") or state.get("last_tool_name") or "")


def _can_retry_transient(state: KernelState) -> bool:
    tool_name = _failed_tool_name(state)
    if not tool_name:
        return False
    counters = state.get("retry_counters") if isinstance(state.get("retry_counters"), dict) else {}
    return int(counters.get(tool_name, 0)) < MAX_TRANSIENT_RETRIES


def _is_sql_or_db_semantic_error(state: KernelState) -> bool:
    telemetry = _error_telemetry(state)
    tool_name = _failed_tool_name(state)
    error_type = str(telemetry.get("error_type") or "").lower()
    if tool_name in {"sql.execute_readonly", "sql.validate"}:
        return True
    semantic_tokens = ("sql", "database", "dbapi", "programmingerror", "operationalerror", "databaseerror", "syntax", "sqlite")
    return any(token in error_type for token in semantic_tokens)


def _reference_sql(state: KernelState) -> str | None:
    reference = resolve_reference(state)
    sql_preview = reference.get("sql_preview")
    return sql_preview.strip() if isinstance(sql_preview, str) and sql_preview.strip() else None


def _revision_reason(state: KernelState) -> str:
    reflection = state.get("agent_reflection") if isinstance(state.get("agent_reflection"), dict) else {}
    critique = reflection.get("sql_critique") if isinstance(reflection.get("sql_critique"), dict) else state.get("agent_sql_critique")
    if isinstance(critique, dict) and critique.get("issues"):
        return "; ".join(str(issue) for issue in critique.get("issues", []))
    telemetry = _error_telemetry(state)
    if telemetry:
        return str(telemetry.get("error_type") or state.get("error") or "Tool execution failed.")
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    return str(execution.get("revise_suggestion") or state.get("error") or latest_user_message(state) or "Revise SQL.")


def _revision_count(state: KernelState) -> int:
    value = state.get("revision_count")
    if isinstance(value, int):
        return value
    return 1 if state.get("revision_attempted") else 0
