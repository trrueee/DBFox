from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from engine.agent.model.system_prompt import build_system_prompt
from engine.agent.model.context_builder import build_context_message, build_progress_guidance_message
from engine.agent.tools.langchain_tools import build_langchain_tools
from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent.graph.message_utils import message_content_text
from engine.agent.progress.fast_path import _max_steps_reason
from engine.agent.app.error_boundary import public_agent_failure, safe_agent_log

import logging
logger = logging.getLogger("dbfox.dbfox_agent.nodes.model_node")

POST_QUERY_ANALYSIS_GRACE_STEPS = 4


@dataclass
class StreamedModelResult:
    message: AIMessage
    text_chunks: list[str]
    has_tool_calls: bool


def _within_post_query_analysis_grace(
    state: DBFoxAgentState,
    *,
    step_count: int,
    max_steps: int,
) -> bool:
    execution = state.get("execution")
    return (
        isinstance(execution, dict)
        and execution.get("success")
        and not state.get("answer")
        and not state.get("final_answer")
        and step_count < max_steps + POST_QUERY_ANALYSIS_GRACE_STEPS
    )


def call_model(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Run the model node without allowing exceptions to escape a LangGraph task."""
    try:
        return _call_model_impl(state, config)
    except Exception as exc:
        return _model_failure_result(exc)


def _model_failure_result(exc: Exception) -> dict[str, Any]:
    failure = public_agent_failure(exc, operation="run")
    safe_agent_log(logger, operation="run", exc=exc)
    return {
        "status": "failed",
        "error": failure.message,
        "trace_events": [
            {
                "type": "agent.model.failed",
                "error": failure.message,
            }
        ],
    }


def _call_model_impl(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    # Hard block: do not invoke the model if we have already reached max_steps.
    # Without this check the model would emit one more set of tool_calls after
    # the step limit was hit, which wastes tokens and can produce confusing
    # ToolMessages for tools that will never execute.
    step_count = int(state.get("step_count", 0))
    max_steps = int(state.get("max_steps", 50))
    if step_count >= max_steps and not _within_post_query_analysis_grace(
        state,
        step_count=step_count,
        max_steps=max_steps,
    ):
        err = _max_steps_reason(state, max_steps)
        return {
            "status": "failed",
            "error": err,
            "trace_events": [
                {
                    "type": "agent.max_steps_exceeded",
                    "step_count": step_count,
                    "max_steps": max_steps,
                }
            ],
        }

    try:
        ctx = graph_context(config)
        registry = ctx.registry

        if not ctx.has_llm_credentials:
            return {
                "messages": [AIMessage(content="Agent requires a configured LLM API key.")],
                "status": "failed",
                "error": "No LLM credentials.",
                "trace_events": [{"type": "agent.model.blocked", "reason": "no_llm_credentials"}],
            }

        allowed_groups = state.get("allowed_tool_groups")
        # None (not []) means "all tools" for backward compatibility.
        # An empty list means "no tools" (pure chat / product_help / database_concept).
        tools = build_langchain_tools(registry, allowed_groups=allowed_groups)

        # Always bind escalate.tool_group so the model can request additional
        # tool groups even when the current plan scope is too narrow.
        escalate_tool = _build_escalate_tool(registry)
        if escalate_tool:
            tools = list(tools)
            tools.append(escalate_tool)

        model = ctx.create_chat_model()
        if tools:
            model_with_tools = model.bind_tools(tools)
        else:
            model_with_tools = model

        messages = [
            SystemMessage(content=build_system_prompt(state)),
            build_context_message(state),
        ]

        progress_msg = build_progress_guidance_message(state)
        if progress_msg is not None:
            messages.append(progress_msg)
        history = state.get("messages", [])

        # Compact message history to prevent context window overflow.
        # Multi-turn ReAct loops accumulate tool messages rapidly —
        # keep the most recent N tool messages, preserve all non-tool messages.
        if len(history) > 20:
            from engine.memory.memory_compactor import compact_messages
            history = compact_messages(list(history))

        messages.extend(history)

        ai_msg = _stream_or_invoke_model_message(
            model_with_tools,
            messages,
            config,
        )

        return {
            "messages": [ai_msg],
            "trace_events": [
                {
                    "type": "agent.model.completed",
                    "content": message_content_text(ai_msg),
                    "tool_calls": getattr(ai_msg, "tool_calls", []) or [],
                }
            ],
            "step_count": state.get("step_count", 0) + 1,
        }
    except Exception as exc:
        return _model_failure_result(exc)


def _stream_or_invoke_model_message(
    model: Any,
    messages: list[Any],
    config: RunnableConfig,
) -> Any:
    stream = getattr(model, "stream", None)
    if not callable(stream):
        return model.invoke(messages, config)

    streamed = _try_stream_model_message(
        model,
        messages,
        config,
    )
    if streamed is None:
        return model.invoke(messages, config)

    return streamed.message


def _try_stream_model_message(
    model: Any,
    messages: list[Any],
    config: RunnableConfig,
) -> StreamedModelResult | None:
    chunks: list[Any] = []
    text_chunks: list[str] = []
    has_tool_call_signal = False
    try:
        try:
            iterator = model.stream(messages, config)
        except TypeError:
            iterator = model.stream(messages)

        for chunk in iterator:
            chunks.append(chunk)
            has_tool_call_signal = has_tool_call_signal or _has_tool_call_signal(chunk)
            text = _raw_message_content_text(chunk)
            if text:
                text_chunks.append(text)
    except Exception:
        return None

    if not chunks:
        return None

    merged = chunks[0]
    try:
        for chunk in chunks[1:]:
            merged = merged + chunk
    except Exception:
        return None

    has_tool_call_signal = has_tool_call_signal or _has_tool_call_signal(merged)
    return StreamedModelResult(
        message=_coerce_ai_message(merged),
        text_chunks=text_chunks,
        has_tool_calls=has_tool_call_signal,
    )


def _coerce_ai_message(message: Any) -> AIMessage:
    if isinstance(message, AIMessage):
        return message
    kwargs: dict[str, Any] = {
        "content": getattr(message, "content", ""),
        "additional_kwargs": getattr(message, "additional_kwargs", {}) or {},
        "response_metadata": getattr(message, "response_metadata", {}) or {},
    }
    message_id = getattr(message, "id", None)
    if message_id is not None:
        kwargs["id"] = message_id
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        kwargs["tool_calls"] = tool_calls
    invalid_tool_calls = getattr(message, "invalid_tool_calls", None)
    if invalid_tool_calls:
        kwargs["invalid_tool_calls"] = invalid_tool_calls
    usage_metadata = getattr(message, "usage_metadata", None)
    if usage_metadata is not None:
        kwargs["usage_metadata"] = usage_metadata
    return AIMessage(**kwargs)


def _raw_message_content_text(message: Any) -> str:
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")


def _has_tool_call_signal(message: Any) -> bool:
    if isinstance(message, dict):
        return bool(
            message.get("tool_calls")
            or message.get("tool_call_chunks")
            or message.get("invalid_tool_calls")
        )
    return bool(
        getattr(message, "tool_calls", None)
        or getattr(message, "tool_call_chunks", None)
        or getattr(message, "invalid_tool_calls", None)
    )


def _build_escalate_tool(registry: Any) -> Any | None:
    """Build a LangChain StructuredTool for escalate.tool_group.

    Returns None if the escalate tool isn't registered (shouldn't happen
    in production, but defensive).
    """
    try:
        rt = registry.get("escalate.tool_group")
        if rt is None:
            return None
    except Exception:
        return None

    from pydantic import BaseModel, Field
    from langchain_core.tools import StructuredTool

    class EscalateInput(BaseModel):
        group: str = Field(description=(
            "Tool group you need: environment, schema, db, semantic, execution, result, chart, sql."
        ))
        reason: str = Field(description="Why you need this tool group.")

    def _noop(**kwargs: Any) -> dict[str, Any]:
        return {"status": "success"}

    return StructuredTool.from_function(
        name="escalate.tool_group",
        description=(
            "Request ADDITIONAL tool groups when the current tool scope is "
            "insufficient. Use when you need a tool from a group that isn't "
            "available to you right now. After calling this, the system expands "
            "your tool access immediately. Only escalate when truly needed."
        ),
        args_schema=EscalateInput,
        func=_noop,
    )

