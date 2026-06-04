from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from engine.agent_kernel.schemas import AgentDecision, ToolCallDecision
from engine.agent_kernel.state import KernelState, latest_user_message


TEXT_PREVIEW_LIMIT = 800
LATEST_ITEM_LIMIT = 5


CONTROLLER_SYSTEM_PROMPT = (
    "You are the DataBox Agent Kernel controller. Choose exactly one next action.\n"
    "Use tools as capabilities, not as a fixed workflow.\n"
    "Decision policy:\n"
    "- For follow-up questions, inspect latest_messages, workspace_context_summary, latest_artifacts, "
    "sql_preview, safe_sql_preview, execution_preview, and recent_tool_results before calling tools.\n"
    "- If the user asks to explain, describe, fix, optimize, or continue from an existing SQL, artifact, "
    "or result, use that context directly; do not restart schema discovery unless the context is missing "
    "or the user asks for a new analysis.\n"
    "- For new analyses, choose the smallest useful tool step and let policy validate execution.\n"
    "- For approval and resume flows, preserve the pending approval/checkpoint context and avoid replanning "
    "or regenerating SQL.\n"
    "- Use update_plan only for meaningful plan changes the user can track.\n"
    "Respect policy and never request execution before SQL has been validated. "
    "Return only JSON matching AgentDecision."
)


def decide_next_action(
    *,
    state: KernelState,
    available_tools: list[dict[str, Any]],
) -> AgentDecision:
    if state.get("api_key"):
        decision = _try_llm_decision(state=state, available_tools=available_tools)
        if decision is not None:
            return decision
    return _fallback_decision(state)


def _try_llm_decision(
    *,
    state: KernelState,
    available_tools: list[dict[str, Any]],
) -> AgentDecision | None:
    api_key = str(state.get("api_key") or "").strip()
    if not api_key:
        return None

    api_base = str(state.get("api_base") or "https://api.openai.com/v1").rstrip("/")
    model_name = str(state.get("model_name") or "gpt-4o-mini")
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": CONTROLLER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "state": _controller_state_view(state),
                        "available_tools": available_tools,
                        "agent_decision_schema": {
                            "action": "call_tool | update_plan | ask_user | final_answer | pause | wait_approval",
                            "tool_call": {"tool_name": "string", "args": {}, "reason": "string"},
                            "plan_patches": [],
                            "user_message": "string | null",
                            "final_answer": "string | null",
                            "confidence": "low | medium | high",
                            "reasoning_summary": "short explanation",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0.0,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
    }
    try:
        response = httpx.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        raw = json.loads(content)
        return AgentDecision.model_validate(raw)
    except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError):
        return None


def _controller_state_view(state: KernelState) -> dict[str, Any]:
    safety = _as_dict(state.get("safety"))
    execution = _as_dict(state.get("execution"))
    return {
        "goal": state.get("goal") or latest_user_message(state),
        "status": state.get("status"),
        "execute": state.get("execute"),
        "latest_messages": _latest_messages(state.get("messages")),
        "latest_artifacts": _latest_artifacts(state.get("artifacts")),
        "pending_approval": _approval_preview(state.get("pending_approval")),
        "sql_preview": _preview_text(state.get("sql")),
        "safe_sql_preview": _preview_text(safety.get("safe_sql") or safety.get("safeSql")),
        "execution_preview": _execution_preview(execution),
        "last_tool_result": _tool_result_preview(_last_mapping(state.get("tool_results")) or state.get("last_observation")),
        "recent_tool_results": [
            item
            for item in (_tool_result_preview(result) for result in _latest_mappings(state.get("tool_results")))
            if item is not None
        ],
        "workspace_context_summary": _workspace_context_summary(state.get("workspace_context")),
        "plan_events": _latest_plan_events(state.get("plan_events")),
        "has_follow_up_context": bool(state.get("follow_up_context")),
        "has_loaded_followup": bool(state.get("followup_context")),
        "has_schema_context": bool(state.get("schema_context")),
        "has_query_plan": bool(state.get("query_plan")),
        "has_sql": bool(state.get("sql")),
        "has_safety": bool(state.get("safety")),
        "safety_can_execute": bool(safety.get("can_execute")),
        "safety_requires_confirmation": bool(safety.get("requires_confirmation")),
        "has_execution": bool(state.get("execution")),
        "has_result_profile": bool(state.get("result_profile")),
        "has_chart_suggestion": bool(state.get("chart_suggestion")),
        "suggestion_count": len(state.get("suggestions", [])),
        "has_answer": bool(state.get("answer")),
        "error": state.get("error"),
        "step_count": state.get("step_count", 0),
        "max_steps": state.get("max_steps", 20),
    }


def _latest_messages(value: Any) -> list[dict[str, str]]:
    messages = _latest_mappings(value)
    compacted: list[dict[str, str]] = []
    for message in messages:
        content = _preview_text(message.get("content"), limit=TEXT_PREVIEW_LIMIT)
        compacted.append(
            {
                "role": str(message.get("role") or "unknown"),
                "content": content or "",
            }
        )
    return compacted


def _latest_artifacts(value: Any) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for artifact in _latest_mappings(value):
        payload = _as_dict(artifact.get("payload"))
        artifacts.append(
            {
                "id": artifact.get("id"),
                "tool_name": artifact.get("tool_name"),
                "kind": artifact.get("kind") or artifact.get("type"),
                "title": artifact.get("title"),
                "payload_preview": _artifact_payload_preview(payload),
            }
        )
    return artifacts


def _artifact_payload_preview(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not payload:
        return None
    preview: dict[str, Any] = {}
    for key in ("sql", "safe_sql", "answer", "summary", "reason", "error"):
        if key in payload:
            preview[key] = _preview_text(payload.get(key))
    if "columns" in payload:
        preview["columns"] = _preview_list(payload.get("columns"))
    row_count = _row_count(payload)
    if row_count is not None:
        preview["row_count"] = row_count
    return preview or {"keys": list(payload.keys())[:LATEST_ITEM_LIMIT]}


def _approval_preview(value: Any) -> dict[str, Any] | None:
    approval = _as_dict(value)
    if not approval:
        return None
    requested_action = _as_dict(approval.get("requested_action"))
    args = _as_dict(requested_action.get("args"))
    return {
        "id": approval.get("id"),
        "status": approval.get("status"),
        "tool_name": requested_action.get("tool_name") or approval.get("tool_name"),
        "step_name": approval.get("step_name"),
        "risk_level": approval.get("risk_level"),
        "reason": _preview_text(approval.get("reason")),
        "requested_args": _compact_mapping(args),
    }


def _execution_preview(execution: dict[str, Any]) -> dict[str, Any] | None:
    if not execution:
        return None
    row_count = _row_count(execution)
    return {
        "success": execution.get("success"),
        "row_count": row_count,
        "columns": _preview_list(execution.get("columns")),
    }


def _tool_result_preview(value: Any) -> dict[str, Any] | None:
    result = _as_dict(value)
    if not result:
        return None
    return {
        "name": result.get("name") or result.get("tool_name"),
        "status": result.get("status"),
        "error": _preview_text(result.get("error")),
        "output_preview": _compact_mapping(_as_dict(result.get("output"))),
    }


def _workspace_context_summary(value: Any) -> dict[str, Any] | None:
    context = _as_dict(value)
    if not context:
        return None
    return {
        "selected_artifact_id": context.get("selected_artifact_id"),
        "recent_agent_run_id": context.get("recent_agent_run_id"),
        "selected_table_names": _preview_list(context.get("selected_table_names")),
        "has_selected_sql": bool(context.get("selected_sql")),
        "has_active_sql": bool(context.get("active_sql")),
        "has_last_query_result_preview": bool(context.get("last_query_result_preview")),
        "selected_sql_preview": _preview_text(context.get("selected_sql") or context.get("active_sql")),
    }


def _latest_plan_events(value: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for event in _latest_mappings(value):
        compacted = {
            "operation": event.get("operation"),
            "step_id": event.get("step_id"),
            "reason": _preview_text(event.get("reason")),
        }
        step = _as_dict(event.get("step"))
        if step:
            compacted["step"] = {
                "id": step.get("id"),
                "title": _preview_text(step.get("title")),
                "status": step.get("status"),
                "tool_name": step.get("tool_name"),
            }
        events.append(compacted)
    return events


def _compact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, item in list(value.items())[:LATEST_ITEM_LIMIT]:
        if isinstance(item, dict):
            compacted[key] = {"keys": list(item.keys())[:LATEST_ITEM_LIMIT]}
        elif isinstance(item, list):
            compacted[key] = _preview_list(item)
        else:
            compacted[key] = _preview_text(item)
    return compacted


def _latest_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_as_dict(item) for item in value[-LATEST_ITEM_LIMIT:] if isinstance(item, dict | BaseModel)]


def _last_mapping(value: Any) -> dict[str, Any] | None:
    latest = _latest_mappings(value)
    return latest[-1] if latest else None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, BaseModel):
        dumped = value.model_dump(mode="json")
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _preview_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:LATEST_ITEM_LIMIT]


def _preview_text(value: Any, *, limit: int = TEXT_PREVIEW_LIMIT) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _row_count(value: dict[str, Any]) -> int | None:
    raw_count = value.get("rowCount", value.get("row_count"))
    if isinstance(raw_count, int):
        return raw_count
    rows = value.get("rows")
    if isinstance(rows, list):
        return len(rows)
    return None


def _fallback_decision(state: KernelState) -> AgentDecision:
    sql_to_explain = _sql_to_explain_from_context(state)
    if sql_to_explain and _is_sql_explanation_request(state):
        return AgentDecision(
            action="final_answer",
            final_answer=_sql_explanation_answer(sql_to_explain),
            confidence="high",
            reasoning_summary="Explain the SQL already selected in the workspace context without restarting data discovery.",
        )

    if state.get("error") and not state.get("revision_attempted") and state.get("sql"):
        return _call("sql.revise", {"sql": state.get("sql"), "error": state.get("error")}, "Revise SQL after the current error.")

    if state.get("answer"):
        answer = state.get("answer") or {}
        return AgentDecision(
            action="final_answer",
            final_answer=str(answer.get("answer") or ""),
            confidence="high",
            reasoning_summary="The answer artifact is ready.",
        )

    if state.get("follow_up_context") and not state.get("followup_context"):
        return _call("followup.load_context", {}, "Normalize prior artifacts for this thread.")

    if not state.get("schema_context"):
        return _call("schema.build_context", {"question": latest_user_message(state)}, "Build schema context before data work.")

    if not state.get("query_plan"):
        return _call("query_plan.build", {}, "Build a query plan from the current schema context.")

    if not state.get("sql"):
        return _call("sql.generate", {}, "Generate a SQL candidate.")

    if not state.get("safety"):
        return _call("sql.validate", {"sql": state.get("sql")}, "Validate SQL before any execution.")

    raw_safety = state.get("safety")
    safety: dict[str, Any] = raw_safety if isinstance(raw_safety, dict) else {}
    if not safety.get("can_execute"):
        if not state.get("revision_attempted"):
            return _call(
                "sql.revise",
                {"sql": state.get("sql"), "error": safety.get("revise_suggestion") or "SQL did not pass TrustGate."},
                "Ask the revision tool for deterministic recovery guidance.",
            )
        return _call("answer.synthesize", {}, "Explain why the agent cannot continue safely.")

    if not state.get("execution"):
        if not state.get("execute", True):
            return _call("sql.skip_execution", {}, "The request is review-only, so execution is skipped.")
        return _call("sql.execute_readonly", {}, "Execute the validated read-only SQL.")

    raw_execution = state.get("execution")
    execution: dict[str, Any] = raw_execution if isinstance(raw_execution, dict) else {}
    if execution.get("success") is False and not state.get("revision_attempted"):
        return _call(
            "sql.revise",
            {"sql": state.get("sql"), "error": execution.get("revise_suggestion") or state.get("error") or "SQL execution failed."},
            "Revise after execution failure.",
        )

    if not state.get("result_profile"):
        return _call("result.profile", {}, "Profile the result for answer synthesis.")

    if not state.get("chart_suggestion"):
        return _call("chart.suggest", {}, "Suggest a chart when the result supports one.")

    if not state.get("suggestions"):
        return _call("followup.suggest", {}, "Suggest useful follow-up questions.")

    return _call("answer.synthesize", {}, "Synthesize the final answer from artifacts.")


def _is_sql_explanation_request(state: KernelState) -> bool:
    text = f"{state.get('goal') or ''}\n{latest_user_message(state)}".lower()
    asks_to_explain = any(token in text for token in ("explain", "describe", "what does", "解释", "说明"))
    mentions_sql = "sql" in text or "query" in text or "查询" in text
    return asks_to_explain and mentions_sql


def _sql_to_explain_from_context(state: KernelState) -> str | None:
    existing_sql = _preview_text(state.get("sql"), limit=TEXT_PREVIEW_LIMIT)
    if existing_sql:
        return existing_sql

    workspace_context = _as_dict(state.get("workspace_context"))
    workspace_sql = _preview_text(workspace_context.get("selected_sql") or workspace_context.get("active_sql"), limit=TEXT_PREVIEW_LIMIT)
    if workspace_sql:
        return workspace_sql

    for context_key in ("follow_up_context", "followup_context"):
        context = _as_dict(state.get(context_key))
        for artifact in _latest_mappings(context.get("artifacts")):
            payload = _as_dict(artifact.get("payload"))
            artifact_sql = _preview_text(payload.get("sql") or payload.get("safe_sql") or artifact.get("summary"), limit=TEXT_PREVIEW_LIMIT)
            if artifact_sql and "select" in artifact_sql.lower():
                return artifact_sql
    return None


def _sql_explanation_answer(sql: str) -> str:
    return (
        "This request is asking about the SQL already selected in the current thread, so no new schema discovery or "
        "query execution is needed.\n\n"
        f"SQL:\n```sql\n{sql}\n```\n\n"
        "At a high level, this is a read-only query. It selects the requested columns or expressions from the referenced "
        "table(s), then applies any filtering, grouping, ordering, or limit clauses shown in the statement."
    )


def _call(tool_name: str, args: dict[str, Any], reason: str) -> AgentDecision:
    return AgentDecision(
        action="call_tool",
        tool_call=ToolCallDecision(tool_name=tool_name, args=args, reason=reason),
        confidence="medium",
        reasoning_summary=reason,
    )
