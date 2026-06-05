from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from engine.agent_kernel.schemas import AgentDecision, ToolCallDecision
from engine.agent_kernel.state import KernelState, latest_user_message


TEXT_PREVIEW_LIMIT = 800
LATEST_ITEM_LIMIT = 5


CONTROLLER_SYSTEM_PROMPT = """
You are the DataBox Agent Kernel controller.

DataBox is a local-first trusted Text-to-SQL data workspace. Choose exactly one next action for the agent.
Return only one valid JSON object matching AgentDecision. Do not write prose outside JSON.

Available actions:
- call_tool: call exactly one DataBox tool.
- update_plan: update the visible non-blocking plan.
- ask_user: ask the user for missing information.
- final_answer: answer from current state, artifacts, SQL, approval, or execution evidence.
- pause: pause the current task.
- wait_approval: wait for the existing approval flow.

Core policy:
1. Tools are capabilities, not a fixed workflow.
2. For follow-up questions, inspect latest_messages, workspace_context_summary, latest_artifacts, pending_approval, sql_preview, safe_sql_preview, execution_preview, and recent_tool_results before calling tools.
3. Do not start schema discovery if the user is asking about an existing SQL, result, chart, artifact, or pending approval.
4. If pending_approval exists and the user asks about SQL, risk, safety, why approval is needed, whether data will change, or what will run, use final_answer from the current state and artifacts.
5. If pending_approval exists and the user wants to modify the SQL, call sql.revise with the current pending SQL and the user's instruction. After revising SQL, it must be validated again before any execution.
6. Never call sql.execute_readonly while pending approval is unresolved.
7. If the user clearly approves or rejects, do not simulate approval or resume in the controller; wait for the approval API flow.
8. If execute=false, never call sql.execute_readonly.
9. If SQL exists but safety is missing, call sql.validate before any execution.
10. If safety.requires_confirmation is true, do not bypass approval.
11. If execution exists and the user asks for interpretation, use answer.synthesize or final_answer based on existing evidence.
12. If the user refers to "this SQL", "this result", "this chart", or "this artifact", prefer workspace_context and latest_artifacts.
13. If a tool failed, prefer sql.revise or ask_user. Do not blindly retry.
14. If enough evidence exists to answer, use final_answer instead of calling more tools.
15. If context is insufficient, use ask_user.
16. If the user changes the goal, use update_plan or ask_user before running tools.
17. **CRITICAL execute=false rule**: If the state shows execution_skipped=true or includes a data_claims_policy field, you MUST NOT make any data-result claims in final_answer. Never say "returned zero rows", "no rows returned", "query executed successfully", "executed successfully", "no students exist", or similar. The correct statement is: "execution was disabled for this review-only run; no result set was retrieved." Row counts from result_profile are meaningless when execution was skipped — do not quote them.

Safety:
- Never invent execution results.
- Never claim data facts unless they come from execution or artifacts.
- Never execute unvalidated SQL.
- Never bypass PolicyGate or TrustGate.
"""


def decide_next_action(
    *,
    state: KernelState,
    available_tools: list[dict[str, Any]],
) -> AgentDecision:
    if state.get("api_key"):
        decision = _try_llm_decision(state=state, available_tools=available_tools)
        if decision is not None:
            # Deterministic sanitizer: strip data-result claims when execution was skipped
            if decision.action == "final_answer" and decision.final_answer:
                decision = _sanitize_final_answer_decision(decision, state)
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
    execution_skipped = bool(
        not execution.get("success")
        and execution.get("reason")
        and ("execute=false" in str(execution.get("reason", "")).lower() or "skipped" in str(execution.get("reason", "")).lower())
    )
    return {
        "goal": state.get("goal") or latest_user_message(state),
        "status": state.get("status"),
        "execute": state.get("execute"),
        "execution_skipped": execution_skipped,
        "latest_messages": _latest_messages(state.get("messages")),
        "latest_artifacts": _latest_artifacts(state.get("artifacts")),
        "pending_approval": _approval_preview(state.get("pending_approval")),
        "sql_preview": _preview_text(state.get("sql")),
        "safe_sql_preview": _preview_text(safety.get("safe_sql") or safety.get("safeSql")),
        "execution_preview": _execution_preview(execution) if not execution_skipped else {"skipped": True, "reason": str(execution.get("reason", ""))},
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
        "has_execution": bool(state.get("execution")) and not execution_skipped,
        "has_result_profile": bool(state.get("result_profile")) and not execution_skipped,
        "has_chart_suggestion": bool(state.get("chart_suggestion")),
        "suggestion_count": len(state.get("suggestions", [])),
        "has_answer": bool(state.get("answer")),
        "error": state.get("error"),
        "step_count": state.get("step_count", 0),
        "max_steps": state.get("max_steps", 20),
        # CRITICAL: when execute=false / execution was skipped, the agent MUST NOT
        # make claims about row counts, empty results, or successful execution.
        "data_claims_policy": (
            "NEVER make data-result claims (e.g. 'returned zero rows', 'no students', "
            "'executed successfully', 'query returned N rows') when execution_skipped=true. "
            "The correct statement is: 'execution was disabled, no result set was retrieved'."
        ) if execution_skipped else None,
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
        "pending_approval_id": context.get("pending_approval_id"),
        "pending_approval_status": context.get("pending_approval_status"),
        "pending_approval_reason": _preview_text(context.get("pending_approval_reason")),
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
    if state.get("error") and not state.get("revision_attempted") and state.get("sql"):
        return _call("sql.revise", {"sql": state.get("sql"), "error": state.get("error")}, "Revise SQL after the current error.")

    # If sql generation failed / unavailable, stop query path and synthesize answer with error context
    if state.get("error") and not state.get("sql") and not state.get("answer"):
        return _call("answer.synthesize", {}, "SQL generation failed — synthesize final answer with error.")

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


def _call(tool_name: str, args: dict[str, Any], reason: str) -> AgentDecision:
    return AgentDecision(
        action="call_tool",
        tool_call=ToolCallDecision(tool_name=tool_name, args=args, reason=reason),
        confidence="medium",
        reasoning_summary=reason,
    )


_SKIPPED_SAFE_TEXT = (
    "I generated and validated the SQL, but execution was disabled "
    "for this review-only run, so no result set was retrieved. "
    "I cannot make data-result claims until the query is executed."
)

_MISLEADING = [
    "returned zero", "no rows returned", "no students",
    "executed successfully", "query executed successfully",
    "returned 0 rows", "returned no results", "0 rows",
    "there are no students", "no data was returned",
    "no matching records", "no results",
]


def _sanitize_final_answer_decision(decision: AgentDecision, state: KernelState) -> AgentDecision:
    """If execution was skipped, replace misleading data claims in the LLM's final_answer."""
    execution = _as_dict(state.get("execution"))
    safety = _as_dict(state.get("safety"))
    sql = state.get("sql")

    # Broad detection: no successful execution + validated SQL = review-only
    execution_ok = bool(execution.get("success"))
    review_only = bool(sql and safety.get("can_execute") and not execution_ok)

    # Also check explicit skip markers
    reason = str(execution.get("reason", "")).lower()
    explicitly_skipped = "execute=false" in reason or "skipped" in reason

    if not review_only and not explicitly_skipped:
        return decision

    text = (decision.final_answer or "").lower()
    needs_sanitize = any(m.lower() in text for m in _MISLEADING)
    if not needs_sanitize:
        return decision

    # Replace with safe text
    return AgentDecision(
        action="final_answer",
        final_answer=_SKIPPED_SAFE_TEXT,
        confidence=decision.confidence,
        reasoning_summary=decision.reasoning_summary,
    )
