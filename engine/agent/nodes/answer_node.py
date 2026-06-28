from __future__ import annotations

import logging
from typing import Any, Callable

from langchain_core.runnables import RunnableConfig

from engine.agent.graph.context import graph_context
from engine.agent.graph.message_utils import is_ai_message, message_content_text, message_tool_calls
from engine.agent.graph.state import DBFoxAgentState

logger = logging.getLogger("dbfox.dbfox_agent.nodes.answer_node")


def synthesize_answer(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Generate the final answer as the only model-streaming answer phase."""
    existing_answer = state.get("answer")
    if isinstance(existing_answer, dict) and existing_answer.get("answer"):
        return {}
    if state.get("pending_approval") or state.get("status") == "waiting_approval":
        return {}

    try:
        ctx = graph_context(config)
    except Exception as exc:
        logger.warning("Skipping answer node; graph context unavailable: %s", exc)
        return {}

    units = _analysis_units(state)
    mode = _answer_mode(state, units)
    answer_context = _build_answer_context(state, mode=mode)
    if ctx.model_name:
        answer_context["runtime_model"] = ctx.model_name

    try:
        from engine.agent_core import answer as answer_module

        answer = answer_module.synthesize_agent_answer(
            question=str(state.get("question") or getattr(ctx.request, "question", "") or ""),
            analysis_units=units,
            mode=mode,
            context=answer_context,
            model_name=ctx.model_name,
            api_key=ctx.api_key,
            api_base=ctx.api_base,
            error=state.get("error"),
            emit_answer_delta=_answer_delta_writer(),
        )
    except Exception as exc:
        logger.warning("Failed to synthesize final answer: %s", exc)
        return {
            "trace_events": [
                {
                    "type": "agent.answer.synthesis_failed",
                    "mode": mode,
                    "error": str(exc),
                }
            ],
        }

    answer_dict = answer.model_dump(mode="json")
    return {
        "answer": answer_dict,
        "final_answer": answer_dict,
        "trace_events": [
            {
                "type": "agent.answer.synthesized",
                "mode": mode,
                "analysis_units": len(units),
                "context_keys": sorted(answer_context.keys()),
                "streaming": True,
            }
        ],
    }


def _answer_mode(state: DBFoxAgentState, units: list[dict[str, Any]]) -> str:
    if units:
        return "evidence"
    if state.get("error"):
        return "failure"
    progress = state.get("progress_decision") or {}
    if isinstance(progress, dict) and progress.get("status") == "clarify":
        return "clarification"
    return "direct"


def _analysis_units(state: DBFoxAgentState) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for unit in state.get("analysis_units") or []:
        if isinstance(unit, dict) and not unit.get("__clear__"):
            units.append(unit)
    return units


def _build_answer_context(state: DBFoxAgentState, *, mode: str) -> dict[str, Any]:
    context: dict[str, Any] = {
        "progress_decision": _dict_or_none(state.get("progress_decision")),
        "workspace_context": _dict_or_none(state.get("workspace_context")),
        "follow_up_context": _dict_or_none(state.get("follow_up_context")),
        "conversation_summary": state.get("conversation_summary"),
        "recent_turns": _dict_list(state.get("recent_turns"))[-4:],
        "active_task": _dict_or_none(state.get("active_task")),
        "reusable_sql_candidates": _dict_list(state.get("reusable_sql_candidates"))[:5],
        "context_summary": state.get("context_summary"),
    }
    if mode == "direct":
        context["direct_context"] = _last_visible_model_text(state)
    else:
        context.update(
            {
                "schema_context": _dict_or_none(state.get("schema_context")),
                "semantic_resolution": _dict_or_none(state.get("semantic_resolution")),
                "sql": state.get("sql"),
                "safety": _dict_or_none(state.get("safety")),
                "execution": _dict_or_none(state.get("execution")),
                "chart_suggestion": _dict_or_none(state.get("chart_suggestion")),
            }
        )
    return {key: value for key, value in context.items() if value not in (None, "", [], {})}


def _last_visible_model_text(state: DBFoxAgentState) -> str:
    for msg in reversed(state.get("messages") or []):
        if is_ai_message(msg) and not message_tool_calls(msg):
            text = message_content_text(msg).strip()
            if text:
                return text[:1200]
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            text = str(msg.get("content") or "").strip()
            if text:
                return text[:1200]
    return ""


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) and not value.get("__clear__") else None


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and not item.get("__clear__")]


def _answer_delta_writer() -> Callable[[str], None] | None:
    try:
        from langgraph.config import get_stream_writer

        stream_writer = get_stream_writer()
    except Exception:
        return None

    def emit(content: str) -> None:
        if content:
            stream_writer({"type": "agent.answer.delta", "content": content})

    return emit
