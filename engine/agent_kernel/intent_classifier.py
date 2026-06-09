from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from engine.agent_kernel.state import KernelState, latest_user_message

# Must stay in sync with lifecycle.AgentIntent.
AgentIntent = str
IntentConfidence = Literal["low", "medium", "high"]

VALID_INTENTS: frozenset[str] = frozenset({
    "new_data_question",
    "followup_on_result",
    "explain_sql",
    "revise_sql",
    "approval_help",
    "chart_request",
    "clarification",
})


class IntentClassification(BaseModel):
    intent: str
    confidence: IntentConfidence
    reason: str = ""
    needs_execution: bool = False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def classify_intent_ai_first(
    state: KernelState,
    *,
    fallback: Callable[[KernelState], AgentIntent],
    api_key: str | None = None,
    api_base: str | None = None,
    model_name: str | None = None,
) -> tuple[AgentIntent, str, dict[str, Any] | None]:
    """Classify user intent AI-first with keyword fallback.

    Returns ``(intent, source, llm_trace)`` where *source* is ``"llm"`` or
    ``"rule_fallback"`` and *llm_trace* is ``None`` when no LLM was attempted,
    or a dict describing the LLM rejection reason when fallback was forced.

    The graph reads only *intent*; *source* and *llm_trace* are for
    observability / debugging.
    """
    api_key = str(api_key or "").strip()
    if not api_key:
        return fallback(state), "rule_fallback", None

    try:
        return _classify_via_llm(
            state,
            api_key,
            fallback=fallback,
            api_base=api_base,
            model_name=model_name,
        )
    except Exception:
        return fallback(state), "rule_fallback", None


# ---------------------------------------------------------------------------
# LLM call + parse
# ---------------------------------------------------------------------------


def _classify_via_llm(
    state: KernelState,
    api_key: str,
    *,
    fallback: Callable[[KernelState], AgentIntent],
    api_base: str | None = None,
    model_name: str | None = None,
) -> tuple[AgentIntent, str, dict[str, Any] | None]:
    api_base = str(api_base or "https://api.openai.com/v1").rstrip("/")
    model_name = str(model_name or "gpt-4o-mini")
    text = latest_user_message(state).strip()

    workspace_context = state.get("workspace_context") if isinstance(state.get("workspace_context"), dict) else {}
    has_sql = bool(state.get("sql") or workspace_context.get("selected_sql") or workspace_context.get("active_sql"))
    has_result = bool(state.get("execution") or workspace_context.get("last_query_result_preview"))
    has_approval = bool(state.get("pending_approval") or workspace_context.get("pending_approval_id"))
    has_workspace_context = bool(workspace_context)
    execute = state.get("execute", True)

    # Lightweight reference hint — never leaks full SQL, rows, or artifact payloads.
    reference_kind: str | None = None
    if workspace_context.get("selected_sql") or workspace_context.get("active_sql"):
        reference_kind = "sql"
    elif state.get("sql"):
        reference_kind = "sql"
    elif state.get("execution"):
        reference_kind = "result"
    elif workspace_context.get("pending_approval_id") or state.get("pending_approval"):
        reference_kind = "approval"

    prompt = _build_intent_classifier_prompt(
        text,
        has_sql=has_sql,
        has_result=has_result,
        has_approval=has_approval,
        has_workspace_context=has_workspace_context,
        execute=execute,
        reference_kind=reference_kind,
    )

    from engine.ai import prepare_chat_payload
    payload = prepare_chat_payload(
        model_name=model_name,
        messages=[
            {"role": "system", "content": "Return exactly one JSON object. No markdown, no extra text."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    response = httpx.post(
        f"{api_base}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    raw = str(payload["choices"][0]["message"]["content"])

    parsed = _parse_intent_json(raw, model_name=model_name)

    # Clarification is the "safe" intent — it pauses and asks the user
    # rather than generating potentially wrong SQL.  Trust it even at
    # low confidence; falling back could reclassify it as
    # new_data_question and start an unwanted pipeline.
    if parsed.intent == "clarification":
        return parsed.intent, "llm", {"llm_candidate": parsed.model_dump()}

    if parsed.confidence == "low":
        llm_trace = {
            "fallback_reason": "llm_low_confidence",
            "llm_candidate": parsed.model_dump(),
        }
        return fallback(state), "rule_fallback", llm_trace

    if parsed.intent not in VALID_INTENTS:
        llm_trace = {
            "fallback_reason": "llm_invalid_intent",
            "llm_candidate": parsed.model_dump(),
        }
        return fallback(state), "rule_fallback", llm_trace

    return parsed.intent, "llm", {"llm_candidate": parsed.model_dump()}


def _parse_intent_json(raw: str, *, model_name: str) -> IntentClassification:
    try:
        data = json.loads(_extract_json_from_text(raw))
        return IntentClassification.model_validate(data)
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError):
        pass

    try:
        repaired = _repair_json_text(raw)
        if repaired != raw:
            data = json.loads(_extract_json_from_text(repaired))
            return IntentClassification.model_validate(data)
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError):
        pass

    raise ValueError(f"Intent classifier returned unparseable JSON (model={model_name}).")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_intent_classifier_prompt(
    text: str,
    *,
    has_sql: bool,
    has_result: bool,
    has_approval: bool,
    has_workspace_context: bool,
    execute: bool,
    reference_kind: str | None,
) -> str:
    options = [
        "new_data_question   - a new data-analysis question",
        "followup_on_result  - asking about a previous result or analysis",
        "explain_sql         - asking to explain existing SQL",
        "revise_sql          - asking to modify, fix, or rewrite SQL",
        "approval_help       - asking about a pending approval or safety decision",
        "chart_request       - requesting a chart or visualization",
        "clarification       - the user needs clarification before proceeding",
    ]
    return json.dumps(
        {
            "task": "Classify the user message into exactly one intent.",
            "message": text,
            "context": {
                "has_sql_in_context": has_sql,
                "has_result_in_context": has_result,
                "has_pending_approval": has_approval,
                "has_workspace_context": has_workspace_context,
                "execute_requested": execute,
                "active_reference_kind": reference_kind,
            },
            "output_schema": {
                "intent": "one of the intent values listed below",
                "confidence": "low | medium | high",
                "reason": "brief justification (1 sentence)",
                "needs_execution": ("boolean: true for new_data_question, followup_on_result, chart_request only"),
            },
            "intent_options": options,
            "rules": [
                "Choose the single best-matching intent. Do not invent new intents.",
                "If the message asks about an existing SQL statement or result, prefer explain_sql, revise_sql, or followup_on_result over new_data_question.",
                "If the message asks for a chart or visualization, use chart_request.",
                "If the message is too vague to classify confidently, use clarification with confidence=low.",
                "Set needs_execution=true only for new_data_question, followup_on_result, and chart_request.",
                "",
                "CRITICAL: You classify user intent only.",
                "Do NOT decide whether SQL is safe to execute.",
                "Do NOT approve execution or bypass approval.",
                "needs_execution is a semantic hint only; actual execution is controlled by the graph, policy, and request.execute flag.",
                "",
                "Return JSON only.",
            ],
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def _extract_json_from_text(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    import re

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in intent classifier response.")
    return match.group(0)


def _repair_json_text(text: str) -> str:
    extracted = _extract_json_from_text(text)
    extracted = extracted.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return extracted
