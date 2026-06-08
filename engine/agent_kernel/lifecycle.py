from __future__ import annotations

from typing import Any, Literal

from engine.agent_kernel.state import KernelState, latest_user_message

AgentIntent = Literal[
    "new_data_question",
    "followup_on_result",
    "explain_sql",
    "revise_sql",
    "approval_help",
    "chart_request",
    "clarification",
]

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


def understand_node(state: KernelState) -> dict[str, Any]:
    """Understand: classify the user's current intent before tool routing."""

    intent = classify_intent(state)
    reference = resolve_reference(state)
    payload = {
        "intent": intent,
        "confidence": _intent_confidence(intent, state, reference),
        "reason": _intent_reason(intent),
        "needs_execution": _intent_needs_execution(intent, state),
        "reference": reference,
    }
    return {
        "status": "running",
        "agent_intent": payload,
        "trace_events": [{"type": "agent.understand", "payload": payload}],
    }


def context_node(state: KernelState) -> dict[str, Any]:
    """Context: summarize reusable workspace/run/artifact context for routing."""

    context = resolve_context(state)
    return {
        "agent_context": context,
        "trace_events": [{"type": "agent.context", "payload": context}],
    }


def plan_node(state: KernelState) -> dict[str, Any]:
    """Plan: create a visible, executable route skeleton for the controller."""

    route = plan_route(state)
    return {
        "agent_lifecycle_plan": route,
        "trace_events": [{"type": "agent.plan", "payload": route}],
    }


def observe_node(state: KernelState) -> dict[str, Any]:
    """Observe: normalize the latest tool result after Act."""

    observation = state.get("last_observation") or {}
    tool_name = state.get("last_tool_name")
    payload = {
        "tool_name": tool_name,
        "status": observation.get("status") if isinstance(observation, dict) else None,
        "has_error": bool((observation or {}).get("error")) if isinstance(observation, dict) else False,
        "output_keys": sorted(((observation or {}).get("output") or {}).keys())[:12]
        if isinstance(observation, dict) and isinstance((observation or {}).get("output"), dict)
        else [],
    }
    return {
        "agent_observation": payload,
        "trace_events": [{"type": "agent.observe", "payload": payload}],
    }


def reflect_node(state: KernelState) -> dict[str, Any]:
    """Reflect: decide whether the loop should continue, revise, ask, or answer."""

    reflection = reflect(state)
    return {
        "agent_reflection": reflection,
        "trace_events": [{"type": "agent.reflect", "payload": reflection}],
    }


def answer_node(state: KernelState) -> dict[str, Any]:
    """Answer: mark the final answer as evidence-aware in lifecycle trace."""

    answer = state.get("answer") or state.get("final_answer") or {}
    payload = {
        "has_answer": bool(answer),
        "answer_preview": _preview((answer or {}).get("answer") if isinstance(answer, dict) else answer),
        "has_execution": bool(state.get("execution")),
        "has_sql": bool(state.get("sql")),
        "artifact_count": len(state.get("artifacts", [])),
        "reference": resolve_reference(state),
    }
    return {
        "trace_events": [{"type": "agent.answer", "payload": payload}],
    }


def classify_intent(state: KernelState) -> AgentIntent:
    text = latest_user_message(state).strip().lower()
    workspace_context = state.get("workspace_context") if isinstance(state.get("workspace_context"), dict) else {}
    reference = resolve_reference(state)
    pending_approval = state.get("pending_approval") or workspace_context.get("pending_approval_id")
    has_result = bool(state.get("execution") or workspace_context.get("last_query_result_preview") or reference.get("kind") == "result")
    has_sql = bool(state.get("sql") or workspace_context.get("selected_sql") or workspace_context.get("active_sql") or reference.get("kind") == "sql")

    approval_words = ("approval", "approve", "confirm", "risk", "safe", "审批", "确认", "风险", "危险", "安全吗", "为什么要")
    revise_words = ("revise", "rewrite", "modify", "change", "fix", "改", "修改", "重写", "修", "换成", "改成")
    explain_words = ("explain", "meaning", "why", "解释", "说明", "什么意思", "为什么")
    chart_words = ("chart", "plot", "visualize", "graph", "图", "图表", "可视化", "柱状", "折线", "饼图")
    followup_words = ("why", "原因", "为什么", "继续", "刚才", "上面", "这个结果", "下降", "增长", "对比")
    clarification_words = ("你是指", "什么意思", "不懂", "clarify")

    if pending_approval and any(word in text for word in approval_words):
        return "approval_help"
    if has_sql and any(word in text for word in revise_words):
        return "revise_sql"
    if has_sql and any(word in text for word in explain_words) and not _looks_like_new_data_question(text):
        return "explain_sql"
    if any(word in text for word in chart_words) and (has_result or has_sql):
        return "chart_request"
    if has_result and any(word in text for word in followup_words):
        return "followup_on_result"
    if any(word in text for word in clarification_words) and not _looks_like_new_data_question(text):
        return "clarification"
    return "new_data_question"


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
    """Resolve pronouns like 'this/that/it/刚才/它' to an active artifact/context.

    Preference order is intentionally deterministic:
    1. explicit workspace selection
    2. pending approval
    3. active state SQL/result
    4. latest matching artifact
    """

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


def plan_route(state: KernelState) -> dict[str, Any]:
    intent_payload = state.get("agent_intent") if isinstance(state.get("agent_intent"), dict) else {}
    intent = str(intent_payload.get("intent") or classify_intent(state))
    reference = intent_payload.get("reference") if isinstance(intent_payload.get("reference"), dict) else resolve_reference(state)
    routes: dict[str, list[str]] = {
        "new_data_question": [
            "schema.build_context",
            "query_plan.build",
            "sql.generate",
            "sql.validate",
            "sql.execute_readonly|sql.skip_execution",
            "result.profile",
            "chart.suggest",
            "followup.suggest",
            "answer.synthesize",
        ],
        "followup_on_result": ["followup.load_context", "result.profile", "answer.synthesize"],
        "explain_sql": ["answer.synthesize"],
        "revise_sql": ["sql.revise", "sql.validate", "answer.synthesize"],
        "approval_help": ["answer.synthesize"],
        "chart_request": ["chart.suggest", "answer.synthesize"],
        "clarification": ["ask_user|answer.synthesize"],
    }
    steps = routes.get(intent, routes["new_data_question"])
    return {
        "intent": intent,
        "route": steps,
        "next_focus": _next_focus(state, steps, reference),
        "is_review_only": not bool(state.get("execute", True)),
        "reference": reference,
    }


def reflect(state: KernelState) -> dict[str, Any]:
    observation = state.get("last_observation") if isinstance(state.get("last_observation"), dict) else {}
    safety = state.get("safety") if isinstance(state.get("safety"), dict) else {}
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    answer = state.get("answer") if isinstance(state.get("answer"), dict) else {}
    reference = resolve_reference(state)

    if state.get("error"):
        if state.get("sql") and not state.get("revision_attempted"):
            action = "revise_sql"
            reason = "The run has an error and SQL exists, so one revision attempt is allowed."
        else:
            action = "stop_with_failure"
            reason = "The run has an unrecoverable error or already attempted revision."
    elif safety and not safety.get("can_execute"):
        action = "revise_or_explain_block"
        reason = "TrustGate blocked execution or requires a safer SQL path."
    elif safety.get("requires_confirmation"):
        action = "wait_approval"
        reason = "The validated SQL requires human approval before execution."
    elif execution.get("success") is False and not state.get("revision_attempted"):
        action = "revise_sql"
        reason = "Execution failed and no revision has been attempted yet."
    elif answer:
        action = "final_answer"
        reason = "An answer artifact exists."
    elif reference.get("kind") in {"sql", "result", "approval"} and classify_intent(state) != "new_data_question":
        action = "use_reference_context"
        reason = "The user referred to existing context, so continue from the resolved reference."
    else:
        action = "continue"
        reason = "More evidence or synthesis is still needed."

    return {
        "action": action,
        "reason": reason,
        "last_tool_name": state.get("last_tool_name"),
        "has_answer": bool(answer),
        "has_execution": bool(execution),
        "reference": reference,
        "last_observation_status": observation.get("status") if isinstance(observation, dict) else None,
    }


def _next_focus(state: KernelState, steps: list[str], reference: dict[str, Any] | None = None) -> str:
    reference = reference or {}
    if reference.get("kind") == "approval" and "answer.synthesize" in steps:
        return "answer.synthesize"
    if reference.get("kind") == "sql" and "sql.revise" in steps and not state.get("safety"):
        return "sql.revise"
    if reference.get("kind") == "sql" and "answer.synthesize" in steps and "sql.revise" not in steps:
        return "answer.synthesize"
    if reference.get("kind") == "result" and "result.profile" in steps and not state.get("result_profile"):
        return "result.profile"
    if not state.get("schema_context") and "schema.build_context" in steps:
        return "schema.build_context"
    if not state.get("query_plan") and "query_plan.build" in steps:
        return "query_plan.build"
    if not state.get("sql") and "sql.generate" in steps:
        return "sql.generate"
    if not state.get("safety") and "sql.validate" in steps:
        return "sql.validate"
    if not state.get("execution") and any(step.startswith("sql.execute") for step in steps):
        return "sql.execute_readonly"
    if not state.get("answer"):
        return "answer.synthesize"
    return "final_answer"


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


def _intent_needs_execution(intent: AgentIntent, state: KernelState) -> bool:
    if not state.get("execute", True):
        return False
    return intent in {"new_data_question", "followup_on_result", "chart_request"}


def _intent_confidence(intent: AgentIntent, state: KernelState, reference: dict[str, Any] | None = None) -> str:
    text = latest_user_message(state).strip()
    reference = reference or {}
    if not text:
        return "low"
    if reference.get("kind") and intent != "new_data_question":
        return "high"
    if intent == "new_data_question":
        return "medium"
    return "high"


def _intent_reason(intent: AgentIntent) -> str:
    return {
        "new_data_question": "Treat the message as a new data question unless existing context clearly changes the route.",
        "followup_on_result": "The user appears to ask about an existing result or prior analysis.",
        "explain_sql": "The user appears to ask for explanation of existing SQL rather than new execution.",
        "revise_sql": "The user appears to request a SQL modification.",
        "approval_help": "The user appears to ask about a pending approval or safety decision.",
        "chart_request": "The user appears to request visualization from existing SQL/result context.",
        "clarification": "The user appears to need clarification before tool execution.",
    }[intent]


def _looks_like_new_data_question(text: str) -> bool:
    query_words = ("多少", "哪些", "排名", "统计", "查询", "销售", "订单", "用户", "gmv", "count", "sum", "top", "average")
    return any(word in text for word in query_words)


def _preview(value: Any, limit: int = 240) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if len(text) <= limit else f"{text[:limit]}..."


def _preview_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:8]
