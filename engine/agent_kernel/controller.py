from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from engine.agent_kernel.schemas import AgentDecision, ToolCallDecision
from engine.agent_kernel.state import KernelState, latest_user_message


TEXT_PREVIEW_LIMIT = 800
LATEST_ITEM_LIMIT = 5


CONTROLLER_SYSTEM_PROMPT = """
You are the DataBox Agent Kernel controller.

Use the seven-step lifecycle state when choosing exactly one next action:
- Understand: agent_intent
- Context: agent_context and workspace_context
- Plan: agent_lifecycle_plan.next_focus
- Act: call exactly one tool through PolicyGate
- Observe: agent_observation and recent_tool_results
- Reflect: agent_reflection
- Answer: only from evidence, artifacts, SQL, approval, safety, or execution

Rules:
- Do not start schema discovery if the user is asking about existing SQL, result, chart, artifact, or pending approval.
- Never execute unvalidated SQL.
- Never bypass PolicyGate or TrustGate.
- If execute=false or execution was skipped, do not make data-result claims.
"""


def decide_next_action(
    *,
    state: KernelState,
    available_tools: list[dict[str, Any]],
) -> AgentDecision:
    return _fallback_decision(state)


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
        "agent_intent": _compact_mapping(_as_dict(state.get("agent_intent"))),
        "agent_context": _compact_mapping(_as_dict(state.get("agent_context"))),
        "agent_lifecycle_plan": _compact_mapping(_as_dict(state.get("agent_lifecycle_plan"))),
        "agent_observation": _compact_mapping(_as_dict(state.get("agent_observation"))),
        "agent_reflection": _compact_mapping(_as_dict(state.get("agent_reflection"))),
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
        "data_claims_policy": (
            "NEVER make data-result claims when execution_skipped=true. "
            "The correct statement is: execution was disabled, no result set was retrieved."
        ) if execution_skipped else None,
    }


def _latest_messages(value: Any) -> list[dict[str, str]]:
    messages = _latest_mappings(value)
    compacted: list[dict[str, str]] = []
    for message in messages:
        content = _preview_text(message.get("content"), limit=TEXT_PREVIEW_LIMIT)
        compacted.append({"role": str(message.get("role") or "unknown"), "content": content or ""})
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
    return {"success": execution.get("success"), "row_count": row_count, "columns": _preview_list(execution.get("columns"))}


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
        compacted = {"operation": event.get("operation"), "step_id": event.get("step_id"), "reason": _preview_text(event.get("reason"))}
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
    return text if len(text) <= limit else f"{text[:limit]}..."


def _row_count(value: dict[str, Any]) -> int | None:
    raw_count = value.get("rowCount", value.get("row_count"))
    if isinstance(raw_count, int):
        return raw_count
    rows = value.get("rows")
    if isinstance(rows, list):
        return len(rows)
    return None


@dataclass(frozen=True)
class FallbackTransition:
    name: str
    predicate: Callable[[KernelState], bool]
    decide: Callable[[KernelState], AgentDecision]


def _fallback_decision(state: KernelState) -> AgentDecision:
    for transition in _FALLBACK_TRANSITIONS:
        if transition.predicate(state):
            return transition.decide(state)
    return _call("answer.synthesize", {}, "Synthesize the final answer from artifacts.")


def _lifecycle_intent(state: KernelState) -> str:
    return str(_as_dict(state.get("agent_intent")).get("intent") or "")


def _lifecycle_reflection_action(state: KernelState) -> str:
    return str(_as_dict(state.get("agent_reflection")).get("action") or "")


def _lifecycle_next_focus(state: KernelState) -> str:
    return str(_as_dict(state.get("agent_lifecycle_plan")).get("next_focus") or "")


def _has_lifecycle_revision_intent(state: KernelState) -> bool:
    return _lifecycle_intent(state) == "revise_sql" and bool(_sql_to_explain_from_context(state)) and not state.get("safety")


def _lifecycle_revision_decision(state: KernelState) -> AgentDecision:
    return _call(
        "sql.revise",
        {"sql": _sql_to_explain_from_context(state), "user_instruction": latest_user_message(state)},
        "Lifecycle intent is revise_sql; revise existing SQL instead of restarting schema discovery.",
    )


def _has_lifecycle_explain_sql_intent(state: KernelState) -> bool:
    return _lifecycle_intent(state) == "explain_sql" and bool(_sql_to_explain_from_context(state))


def _lifecycle_explain_sql_decision(state: KernelState) -> AgentDecision:
    if _should_inline_workspace_sql_explanation(state):
        return _inline_workspace_sql_explanation(state)
    workspace_tool = _workspace_tool_from_state(state)
    if workspace_tool:
        return _call(workspace_tool, {"question": latest_user_message(state)}, "Lifecycle intent is explain_sql; use workspace SQL context.")
    return AgentDecision(
        action="final_answer",
        final_answer=_sql_explanation_answer(_sql_to_explain_from_context(state) or ""),
        confidence="high",
        reasoning_summary="Explain existing SQL from lifecycle context without schema discovery.",
    )


def _has_lifecycle_approval_help_intent(state: KernelState) -> bool:
    return _lifecycle_intent(state) == "approval_help" and bool(state.get("pending_approval") or _as_dict(state.get("workspace_context")).get("pending_approval_id"))


def _lifecycle_approval_help_decision(state: KernelState) -> AgentDecision:
    approval = _approval_preview(state.get("pending_approval")) or _workspace_context_summary(state.get("workspace_context")) or {}
    return AgentDecision(
        action="final_answer",
        final_answer=(
            "This run is waiting for approval before the agent can continue. "
            "The controller will not execute the pending action or simulate approval in chat. "
            f"Approval context: {json.dumps(approval, ensure_ascii=False, default=str)}"
        ),
        confidence="high",
        reasoning_summary="Lifecycle intent is approval_help; explain the existing approval instead of calling tools.",
    )


def _has_lifecycle_chart_request(state: KernelState) -> bool:
    return _lifecycle_intent(state) == "chart_request" and not bool(state.get("chart_suggestion"))


def _lifecycle_chart_decision(state: KernelState) -> AgentDecision:
    return _call("chart.suggest", {}, "Lifecycle intent is chart_request; suggest a chart from existing result context.")


def _has_reflection_revision(state: KernelState) -> bool:
    return _lifecycle_reflection_action(state) == "revise_sql" and bool(state.get("sql")) and not state.get("revision_attempted")


def _reflection_revision_decision(state: KernelState) -> AgentDecision:
    execution = _as_dict(state.get("execution"))
    return _call(
        "sql.revise",
        {"sql": state.get("sql"), "error": execution.get("revise_suggestion") or state.get("error") or "Agent reflection requested SQL revision."},
        "Agent reflection requested one SQL revision before continuing.",
    )


def _has_lifecycle_next_focus(state: KernelState, tool_name: str) -> bool:
    return _lifecycle_next_focus(state) == tool_name


def _can_inline_workspace_sql_explanation(state: KernelState) -> bool:
    sql_to_explain = _sql_to_explain_from_context(state)
    return bool(sql_to_explain and _is_sql_explanation_request(state) and _should_inline_workspace_sql_explanation(state))


def _inline_workspace_sql_explanation(state: KernelState) -> AgentDecision:
    sql_to_explain = _sql_to_explain_from_context(state) or ""
    return AgentDecision(
        action="final_answer",
        final_answer=_sql_explanation_answer(sql_to_explain),
        confidence="high",
        reasoning_summary="Explain the selected SQL directly without restarting data discovery.",
    )


def _has_workspace_assist(state: KernelState) -> bool:
    workspace_tool = _workspace_tool_from_state(state)
    return bool(workspace_tool and not state.get("tool_results"))


def _workspace_assist_decision(state: KernelState) -> AgentDecision:
    workspace_tool = _workspace_tool_from_state(state) or "workspace.continue_from_artifact"
    return _call(workspace_tool, {"question": latest_user_message(state)}, "Use the active workspace context without restarting data discovery.")


def _recover_or_stop_on_error(state: KernelState) -> AgentDecision:
    if not state.get("revision_attempted") and state.get("sql"):
        return _call("sql.revise", {"sql": state.get("sql"), "error": state.get("error")}, "Revise SQL after the current error.")
    return AgentDecision(
        action="final_answer",
        final_answer=f"I could not complete the analysis because: {state.get('error')}",
        confidence="high",
        reasoning_summary="Stop after the unrecoverable tool or policy error.",
    )


def _return_ready_answer(state: KernelState) -> AgentDecision:
    answer = _as_dict(state.get("answer"))
    return AgentDecision(action="final_answer", final_answer=str(answer.get("answer") or ""), confidence="high", reasoning_summary="The answer artifact is ready.")


def _load_followup_context(state: KernelState) -> AgentDecision:
    return _call("followup.load_context", {}, "Normalize prior artifacts for this thread.")


def _build_schema_context(state: KernelState) -> AgentDecision:
    return _call("schema.build_context", {"question": latest_user_message(state)}, "Build schema context before data work.")


def _build_query_plan(state: KernelState) -> AgentDecision:
    return _call("query_plan.build", {}, "Build a query plan from the current schema context.")


def _generate_sql(state: KernelState) -> AgentDecision:
    return _call("sql.generate", {}, "Generate a SQL candidate.")


def _validate_sql(state: KernelState) -> AgentDecision:
    return _call("sql.validate", {"sql": state.get("sql")}, "Validate SQL before any execution.")


def _sql_is_blocked_by_policy(state: KernelState) -> bool:
    safety = _as_dict(state.get("safety"))
    return bool(safety and not safety.get("can_execute"))


def _policy_block_decision(state: KernelState) -> AgentDecision:
    safety = _as_dict(state.get("safety"))
    blocked_reasons = [str(reason) for reason in safety.get("blocked_reasons", [])]
    hard_blockers = [reason for reason in blocked_reasons if reason != "requires_confirmation"]
    if safety.get("requires_confirmation") and not hard_blockers:
        if not state.get("execute", True):
            return _call("sql.skip_execution", {}, "The request is review-only, so execution is skipped.")
        return _call("sql.execute_readonly", {}, "Route confirmed SQL execution through policy approval.")
    if not state.get("revision_attempted"):
        return _call("sql.revise", {"sql": state.get("sql"), "error": safety.get("revise_suggestion") or "SQL did not pass TrustGate."}, "Ask the revision tool for deterministic recovery guidance.")
    return _call("answer.synthesize", {}, "Explain why the agent cannot continue safely.")


def _needs_execution_decision(state: KernelState) -> bool:
    return not bool(state.get("execution"))


def _execution_decision(state: KernelState) -> AgentDecision:
    if not state.get("execute", True):
        return _call("sql.skip_execution", {}, "The request is review-only, so execution is skipped.")
    return _call("sql.execute_readonly", {}, "Execute the validated read-only SQL.")


def _execution_failed_without_revision(state: KernelState) -> bool:
    execution = _as_dict(state.get("execution"))
    return bool(execution.get("success") is False and not state.get("revision_attempted"))


def _revise_after_execution_failure(state: KernelState) -> AgentDecision:
    execution = _as_dict(state.get("execution"))
    return _call("sql.revise", {"sql": state.get("sql"), "error": execution.get("revise_suggestion") or state.get("error") or "SQL execution failed."}, "Revise after execution failure.")


_FALLBACK_TRANSITIONS: tuple[FallbackTransition, ...] = (
    FallbackTransition("lifecycle_approval_help", _has_lifecycle_approval_help_intent, _lifecycle_approval_help_decision),
    FallbackTransition("lifecycle_explain_sql", _has_lifecycle_explain_sql_intent, _lifecycle_explain_sql_decision),
    FallbackTransition("lifecycle_revision", _has_lifecycle_revision_intent, _lifecycle_revision_decision),
    FallbackTransition("lifecycle_chart_request", _has_lifecycle_chart_request, _lifecycle_chart_decision),
    FallbackTransition("reflection_revision", _has_reflection_revision, _reflection_revision_decision),
    FallbackTransition("inline_workspace_sql_explanation", _can_inline_workspace_sql_explanation, _inline_workspace_sql_explanation),
    FallbackTransition("workspace_assist", _has_workspace_assist, _workspace_assist_decision),
    FallbackTransition("recover_or_stop_on_error", lambda state: bool(state.get("error")), _recover_or_stop_on_error),
    FallbackTransition("return_ready_answer", lambda state: bool(state.get("answer")), _return_ready_answer),
    FallbackTransition("load_followup_context", lambda state: bool(state.get("follow_up_context") and not state.get("followup_context")), _load_followup_context),
    FallbackTransition("build_schema_context", lambda state: not bool(state.get("schema_context")) and _has_lifecycle_next_focus(state, "schema.build_context"), _build_schema_context),
    FallbackTransition("build_query_plan", lambda state: not bool(state.get("query_plan")) and _has_lifecycle_next_focus(state, "query_plan.build"), _build_query_plan),
    FallbackTransition("generate_sql", lambda state: not bool(state.get("sql")) and _has_lifecycle_next_focus(state, "sql.generate"), _generate_sql),
    FallbackTransition("validate_sql", lambda state: not bool(state.get("safety")) and _has_lifecycle_next_focus(state, "sql.validate"), _validate_sql),
    FallbackTransition("build_schema_context_default", lambda state: not bool(state.get("schema_context")), _build_schema_context),
    FallbackTransition("build_query_plan_default", lambda state: not bool(state.get("query_plan")), _build_query_plan),
    FallbackTransition("generate_sql_default", lambda state: not bool(state.get("sql")), _generate_sql),
    FallbackTransition("validate_sql_default", lambda state: not bool(state.get("safety")), _validate_sql),
    FallbackTransition("policy_block", _sql_is_blocked_by_policy, _policy_block_decision),
    FallbackTransition("execute_or_skip_sql", _needs_execution_decision, _execution_decision),
    FallbackTransition("revise_execution_failure", _execution_failed_without_revision, _revise_after_execution_failure),
    FallbackTransition("profile_result", lambda state: not bool(state.get("result_profile")), lambda state: _call("result.profile", {}, "Profile the result for answer synthesis.")),
    FallbackTransition("suggest_chart", lambda state: not bool(state.get("chart_suggestion")), lambda state: _call("chart.suggest", {}, "Suggest a chart when the result supports one.")),
    FallbackTransition("suggest_followups", lambda state: not bool(state.get("suggestions")), lambda state: _call("followup.suggest", {}, "Suggest useful follow-up questions.")),
    FallbackTransition("synthesize_answer", lambda _state: True, lambda _state: _call("answer.synthesize", {}, "Synthesize the final answer from artifacts.")),
)


def _is_sql_explanation_request(state: KernelState) -> bool:
    text = f"{state.get('goal') or ''}\n{latest_user_message(state)}".lower()
    asks_to_explain = any(token in text for token in ("explain", "describe", "what does", "解释", "说明"))
    mentions_sql = "sql" in text or "query" in text or "查询" in text
    return asks_to_explain and mentions_sql


def _workspace_tool_from_state(state: KernelState) -> str | None:
    workspace_context = _as_dict(state.get("workspace_context"))
    text = f"{state.get('goal') or ''}\n{latest_user_message(state)}".lower()
    has_sql = bool(workspace_context.get("selected_sql") or workspace_context.get("active_sql"))
    if has_sql:
        if any(token in text for token in ("fix", "error", "修复", "错误")):
            return "workspace.fix_sql"
        if any(token in text for token in ("optimize", "优化")):
            return "workspace.optimize_sql"
        if any(token in text for token in ("rewrite", "重写", "修改", "改成", "换成")):
            return "workspace.rewrite_sql"
        if any(token in text for token in ("explain", "describe", "what does", "解释", "说明")):
            return "workspace.explain_sql"
    if workspace_context.get("last_query_result_preview") and any(token in text for token in ("result", "结果", "explain", "解释", "说明")):
        return "workspace.explain_result"
    if workspace_context.get("selected_artifact_id") and any(token in text for token in ("continue", "继续")):
        return "workspace.continue_from_artifact"
    if workspace_context.get("selected_table_names") and any(token in text for token in ("schema", "table", "表结构", "字段")):
        return "workspace.explain_schema"
    return None


def _should_inline_workspace_sql_explanation(state: KernelState) -> bool:
    workspace_context = _as_dict(state.get("workspace_context"))
    return bool(workspace_context.get("selected_sql")) and not bool(workspace_context.get("active_sql"))


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
        "This request is asking about the SQL already selected in the current thread, so no new schema discovery or query execution is needed.\n\n"
        f"SQL:\n```sql\n{sql}\n```\n\n"
        "At a high level, this is a read-only query. It selects the requested columns or expressions from the referenced table(s), then applies any filtering, grouping, ordering, or limit clauses shown in the statement."
    )


def _call(tool_name: str, args: dict[str, Any], reason: str) -> AgentDecision:
    return AgentDecision(action="call_tool", tool_call=ToolCallDecision(tool_name=tool_name, args=args, reason=reason), confidence="medium", reasoning_summary=reason)


def _review_only_without_execution(state: KernelState) -> bool:
    execution = _as_dict(state.get("execution"))
    safety = _as_dict(state.get("safety"))
    sql = state.get("sql")
    if execution.get("success"):
        return False
    reason = str(execution.get("reason", "")).lower()
    explicitly_skipped = "execute=false" in reason or "skipped" in reason
    return explicitly_skipped or bool(sql and safety.get("can_execute"))
