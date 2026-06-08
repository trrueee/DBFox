from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from engine.agent_kernel.schemas import AgentDecision, ToolCallDecision
from engine.agent_kernel.state import KernelState, latest_user_message


TEXT_PREVIEW_LIMIT = 800


CONTROLLER_SYSTEM_PROMPT = """
You are the DataBox Agent Kernel emergency fallback controller.
The LangGraph topology owns the Text-to-SQL control flow.
Do not start schema discovery, query planning, SQL generation, validation, execution, profiling, charting, or follow-up generation from this controller.
Only handle existing answers, approval explanations, workspace-local help, graph errors, and last-resort synthesis from existing artifacts.
"""


def decide_next_action(
    *,
    state: KernelState,
    available_tools: list[dict[str, Any]],
) -> AgentDecision:
    return _fallback_decision(state)


def _fallback_decision(state: KernelState) -> AgentDecision:
    if state.get("answer"):
        answer = _as_dict(state.get("answer"))
        return AgentDecision(
            action="final_answer",
            final_answer=str(answer.get("answer") or ""),
            confidence="high",
            reasoning_summary="Return existing answer from graph state.",
        )

    if state.get("pending_approval") or _as_dict(state.get("workspace_context")).get("pending_approval_id"):
        approval = _approval_preview(state.get("pending_approval")) or _workspace_context_summary(state.get("workspace_context")) or {}
        return AgentDecision(
            action="final_answer",
            final_answer=(
                "This run is waiting for approval before the pending action can continue. "
                "I will not simulate approval or execute the pending action in chat. "
                f"Approval context: {json.dumps(approval, ensure_ascii=False, default=str)}"
            ),
            confidence="high",
            reasoning_summary="Explain pending approval from existing state.",
        )

    workspace_tool = _workspace_tool_from_state(state)
    if workspace_tool:
        return _call(workspace_tool, {"question": latest_user_message(state)}, "Use active workspace context only.")

    if state.get("error"):
        return AgentDecision(
            action="final_answer",
            final_answer=f"I could not complete the request because: {state.get('error')}",
            confidence="high",
            reasoning_summary="Stop after graph error.",
        )

    return _call("answer.synthesize", {}, "Last-resort synthesis from existing artifacts only.")


def _controller_state_view(state: KernelState) -> dict[str, Any]:
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
        "agent_intent": _as_dict(state.get("agent_intent")),
        "agent_context": _as_dict(state.get("agent_context")),
        "agent_observation": _as_dict(state.get("agent_observation")),
        "agent_reflection": _as_dict(state.get("agent_reflection")),
        "pending_approval": _approval_preview(state.get("pending_approval")),
        "workspace_context_summary": _workspace_context_summary(state.get("workspace_context")),
        "has_answer": bool(state.get("answer")),
        "error": state.get("error"),
    }


def _approval_preview(value: Any) -> dict[str, Any] | None:
    approval = _as_dict(value)
    if not approval:
        return None
    requested_action = _as_dict(approval.get("requested_action"))
    return {
        "id": approval.get("id"),
        "status": approval.get("status"),
        "tool_name": requested_action.get("tool_name") or approval.get("tool_name"),
        "risk_level": approval.get("risk_level"),
        "reason": _preview_text(approval.get("reason")),
    }


def _workspace_context_summary(value: Any) -> dict[str, Any] | None:
    context = _as_dict(value)
    if not context:
        return None
    return {
        "selected_artifact_id": context.get("selected_artifact_id"),
        "pending_approval_id": context.get("pending_approval_id"),
        "pending_approval_status": context.get("pending_approval_status"),
        "has_selected_sql": bool(context.get("selected_sql")),
        "has_active_sql": bool(context.get("active_sql")),
        "has_last_query_result_preview": bool(context.get("last_query_result_preview")),
        "selected_sql_preview": _preview_text(context.get("selected_sql") or context.get("active_sql")),
    }


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


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, BaseModel):
        dumped = value.model_dump(mode="json")
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _preview_text(value: Any, *, limit: int = TEXT_PREVIEW_LIMIT) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    text = text.strip()
    return text if len(text) <= limit else f"{text[:limit]}..."


def _call(tool_name: str, args: dict[str, Any], reason: str) -> AgentDecision:
    return AgentDecision(
        action="call_tool",
        tool_call=ToolCallDecision(tool_name=tool_name, args=args, reason=reason),
        confidence="medium",
        reasoning_summary=reason,
    )
