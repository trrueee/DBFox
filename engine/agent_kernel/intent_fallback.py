from __future__ import annotations

from typing import Any, Literal

from engine.agent_kernel.state import KernelState, latest_user_message
from engine.agent_kernel.reference_resolver import resolve_reference

AgentIntent = Literal[
    "new_data_question",
    "followup_on_result",
    "explain_sql",
    "revise_sql",
    "approval_help",
    "chart_request",
    "clarification",
]

FALLBACK_INTENT_KEYWORDS = {
    "approval_help": ("approval", "approve", "confirm", "risk", "safe", "审批", "确认", "风险", "危险", "安全吗", "为什么要"),
    "revise_sql": ("revise", "rewrite", "modify", "change", "fix", "改", "修改", "重写", "修", "换成", "改成"),
    "explain_sql": ("explain", "meaning", "why", "解释", "说明", "什么意思", "为什么"),
    "chart_request": ("chart", "plot", "visualize", "graph", "图", "图表", "可视化", "柱状", "折线", "饼图"),
    "followup_on_result": ("why", "原因", "为什么", "继续", "刚才", "上面", "这个结果", "下降", "增长", "对比"),
    "clarification": ("你是指", "什么意思", "不懂", "clarify"),
}


def classify_intent_fallback(state: KernelState) -> AgentIntent:
    text = latest_user_message(state).strip().lower()
    workspace_context = state.get("workspace_context") if isinstance(state.get("workspace_context"), dict) else {}
    reference = resolve_reference(state)
    pending_approval = state.get("pending_approval") or workspace_context.get("pending_approval_id")
    has_result = bool(state.get("execution") or workspace_context.get("last_query_result_preview") or reference.get("kind") == "result")
    has_sql = bool(state.get("sql") or workspace_context.get("selected_sql") or workspace_context.get("active_sql") or reference.get("kind") == "sql")

    if pending_approval and any(word in text for word in FALLBACK_INTENT_KEYWORDS["approval_help"]):
        return "approval_help"
    if has_sql and any(word in text for word in FALLBACK_INTENT_KEYWORDS["revise_sql"]):
        return "revise_sql"
    if has_sql and any(word in text for word in FALLBACK_INTENT_KEYWORDS["explain_sql"]) and not _looks_like_new_data_question(text):
        return "explain_sql"
    if any(word in text for word in FALLBACK_INTENT_KEYWORDS["chart_request"]) and (has_result or has_sql):
        return "chart_request"
    if has_result and any(word in text for word in FALLBACK_INTENT_KEYWORDS["followup_on_result"]):
        return "followup_on_result"
    if any(word in text for word in FALLBACK_INTENT_KEYWORDS["clarification"]) and not _looks_like_new_data_question(text):
        return "clarification"
    return "new_data_question"


def _looks_like_new_data_question(text: str) -> bool:
    query_words = ("多少", "哪些", "排名", "统计", "查询", "销售", "订单", "用户", "gmv", "count", "sum", "top", "average")
    return any(word in text for word in query_words)


# DEPRECATED — backward compatibility alias.
classify_intent = classify_intent_fallback
