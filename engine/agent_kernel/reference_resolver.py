from __future__ import annotations

from typing import Any

from engine.agent_kernel.state import KernelState, latest_user_message

REFERENCE_WORDS = (
    "this",
    "that",
    "it",
    "previous",
    "last",
    "above",
    "current",
    "这个",
    "那个",
    "它",
    "刚才",
    "上面",
    "当前",
    "之前",
)


def resolve_context(state: KernelState) -> dict[str, Any]:
    workspace_context = state.get("workspace_context") if isinstance(state.get("workspace_context"), dict) else {}
    safety = state.get("safety") if isinstance(state.get("safety"), dict) else {}
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    reference = resolve_reference(state)
    return {
        "datasource_id": state.get("datasource_id"),
        "resolved_reference": reference,
        "has_workspace_context": bool(workspace_context),
        "has_follow_up_context": bool(state.get("follow_up_context") or state.get("followup_context")),
        "has_selected_sql": bool(workspace_context.get("selected_sql") or workspace_context.get("active_sql") or state.get("sql") or reference.get("kind") == "sql"),
        "has_pending_approval": bool(state.get("pending_approval") or workspace_context.get("pending_approval_id") or reference.get("kind") == "approval"),
        "has_schema_context": bool(state.get("schema_context")),
        "has_query_plan": bool(state.get("query_plan")),
        "has_sql": bool(state.get("sql") or reference.get("kind") == "sql"),
        "has_safety": bool(safety),
        "safety_can_execute": bool(safety.get("can_execute")),
        "safety_requires_confirmation": bool(safety.get("requires_confirmation")),
        "has_execution": bool(execution or reference.get("kind") == "result"),
        "execution_success": execution.get("success") if execution else None,
        "has_result_profile": bool(state.get("result_profile")),
        "has_chart_suggestion": bool(state.get("chart_suggestion")),
        "artifact_count": len(state.get("artifacts", [])),
    }


def resolve_reference(state: KernelState) -> dict[str, Any]:
    """Resolve pronouns like 'this/that/it/刚才/它' to an active artifact/context."""
    text = latest_user_message(state).strip().lower()
    has_reference_language = any(word in text for word in REFERENCE_WORDS)
    workspace_context = state.get("workspace_context") if isinstance(state.get("workspace_context"), dict) else {}

    selected_sql = workspace_context.get("selected_sql") or workspace_context.get("active_sql")
    if selected_sql:
        return {
            "kind": "sql",
            "source": "workspace_context",
            "id": workspace_context.get("selected_artifact_id") or workspace_context.get("recent_agent_run_id"),
            "confidence": "high" if has_reference_language else "medium",
            "sql_preview": _preview(selected_sql),
        }

    pending_approval = state.get("pending_approval") or workspace_context.get("pending_approval_id")
    if pending_approval:
        return {
            "kind": "approval",
            "source": "pending_approval",
            "id": pending_approval.get("id") if isinstance(pending_approval, dict) else pending_approval,
            "confidence": "high" if has_reference_language else "medium",
        }

    if state.get("sql"):
        return {
            "kind": "sql",
            "source": "state.sql",
            "id": None,
            "confidence": "high" if has_reference_language else "medium",
            "sql_preview": _preview(state.get("sql")),
        }

    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    if execution:
        return {
            "kind": "result",
            "source": "state.execution",
            "id": execution.get("executionId") or execution.get("historyId"),
            "confidence": "high" if has_reference_language else "medium",
            "row_count": execution.get("rowCount", execution.get("row_count")),
            "columns": _preview_list(execution.get("columns")),
        }

    latest_artifact = _latest_relevant_artifact(state)
    if latest_artifact:
        return latest_artifact

    return {"kind": None, "source": None, "id": None, "confidence": "low"}


def _latest_relevant_artifact(state: KernelState) -> dict[str, Any] | None:
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), list) else []
    for artifact in reversed([item for item in artifacts if isinstance(item, dict)]):
        payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
        semantic_id = str(artifact.get("semantic_id") or artifact.get("id") or "")
        artifact_type = str(artifact.get("type") or artifact.get("kind") or "")
        sql = payload.get("sql") or payload.get("safe_sql") or payload.get("raw_sql")
        if sql:
            return {
                "kind": "sql",
                "source": "artifact",
                "id": artifact.get("id") or semantic_id,
                "semantic_id": semantic_id,
                "confidence": "medium",
                "sql_preview": _preview(sql),
            }
        if artifact_type in {"table", "result", "result_table"} or semantic_id == "result_table":
            return {
                "kind": "result",
                "source": "artifact",
                "id": artifact.get("id") or semantic_id,
                "semantic_id": semantic_id,
                "confidence": "medium",
                "row_count": payload.get("rowCount", payload.get("row_count")),
                "columns": _preview_list(payload.get("columns")),
            }
        if artifact_type == "approval" or semantic_id == "approval":
            return {
                "kind": "approval",
                "source": "artifact",
                "id": artifact.get("id") or semantic_id,
                "semantic_id": semantic_id,
                "confidence": "medium",
            }
    return None


def _preview(value: Any, limit: int = 240) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if len(text) <= limit else f"{text[:limit]}..."


def _preview_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:8]
