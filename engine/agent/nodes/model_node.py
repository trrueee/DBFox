from __future__ import annotations

from typing import Any
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from engine.llm import get_chat_model
from engine.agent.model.system_prompt import build_system_prompt
from engine.agent.model.context_builder import build_context_message, build_progress_guidance_message
from engine.agent.tools.langchain_tools import build_langchain_tools
from engine.agent.graph.state import DataBoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent.graph.message_utils import first_user_text, message_content_text, message_tool_calls
from engine.agent.progress.fast_path import _max_steps_reason
from engine.agent.tools.tool_aliases import to_internal

import logging
logger = logging.getLogger("databox.databox_agent.nodes.model_node")

POST_QUERY_ANALYSIS_GRACE_STEPS = 4


def _within_post_query_analysis_grace(
    state: DataBoxAgentState,
    *,
    step_count: int,
    max_steps: int,
) -> bool:
    execution = state.get("execution")
    return (
        isinstance(execution, dict)
        and execution.get("success")
        and not state.get("result_profile")
        and not state.get("answer")
        and not state.get("final_answer")
        and step_count < max_steps + POST_QUERY_ANALYSIS_GRACE_STEPS
    )


def call_model(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    # Hard block: do not invoke the model if we have already reached max_steps.
    # Without this check the model would emit one more set of tool_calls after
    # the step limit was hit, which wastes tokens and can produce confusing
    # ToolMessages for tools that will never execute.
    step_count = int(state.get("step_count", 0))
    max_steps = int(state.get("max_steps", 20))
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

    ctx = graph_context(config)
    model_name = ctx.model_name
    api_key = ctx.api_key
    api_base = ctx.api_base
    registry = ctx.registry

    if not ctx.has_llm_credentials:
        from langchain_core.messages import AIMessage
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

    model = get_chat_model(
        model_name=model_name,
        api_key=api_key,
        api_base=api_base,
    )
    if tools:
        model_with_tools = model.bind_tools(tools)
    else:
        model_with_tools = model

    messages = [
        SystemMessage(content=build_system_prompt(state)),
        build_context_message(state),
    ]

    # Auto-inject memory context on first model turn (migrated from deleted planner).
    # Subsequent turns already have this context in the conversation history.
    if int(state.get("step_count", 0)) == 0:
        memory_ctx = _get_memory_context(state)
        if memory_ctx:
            messages.append(SystemMessage(content=memory_ctx))

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

    raw_msg = model_with_tools.invoke(messages, config)
    ai_msg = _with_visible_tool_call_content(raw_msg)

    # Dispatch custom event to LangSmith so the visible content is traceable
    # even when the raw LLM response has empty content with tool_calls.
    visible_content = message_content_text(ai_msg)
    tool_calls = getattr(ai_msg, "tool_calls", []) or []
    try:
        from langchain_core.callbacks.manager import dispatch_custom_event
        dispatch_custom_event(
            name="agent.model.completed",
            data={
                "content": visible_content,
                "tool_calls": [
                    {"name": tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")}
                    for tc in tool_calls
                ],
                "raw_content_empty": not message_content_text(raw_msg),
            },
            config=config,
        )
    except Exception:
        pass  # best-effort: LangSmith tracing is optional

    return {
        "messages": [ai_msg],
        "trace_events": [
            {
                "type": "agent.model.completed",
                "content": visible_content,
                "tool_calls": tool_calls,
            }
        ],
        "step_count": state.get("step_count", 0) + 1,
    }


def _with_visible_tool_call_content(ai_msg: Any) -> Any:
    """Add a concise visible plan when a provider returns tool_calls-only content."""
    if message_content_text(ai_msg):
        return ai_msg
    tool_calls = message_tool_calls(ai_msg)
    if not tool_calls:
        return ai_msg

    names: list[str] = []
    for call in tool_calls[:3]:
        if isinstance(call, dict):
            raw_name = str(call.get("name") or "")
        else:
            raw_name = str(getattr(call, "name", "") or "")
        if raw_name:
            names.append(to_internal(raw_name))
    if not names:
        return ai_msg

    visible_content = f"准备调用工具：{', '.join(names)}"
    try:
        return ai_msg.model_copy(update={"content": visible_content})
    except Exception:
        try:
            ai_msg.content = visible_content
        except Exception:
            pass
        return ai_msg


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
            "Tool group you need: workspace, environment, schema, db, semantic, memory."
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


def _get_memory_context(state: DataBoxAgentState) -> str:
    """Auto-inject relevant long-term memory into the first model turn.

    Migrated from the deleted planner_node.  Searches for user preferences,
    project rules, past successful trajectories, metric definitions, and
    schema aliases — then formats them as a SystemMessage for the LLM.

    Best-effort: exceptions are logged but never block the model call.
    """
    try:
        from engine.agent.memory_bridge import search_memory_for_planner

        messages = state.get("messages", [])
        question = first_user_text(messages)
        if not question:
            return ""

        return search_memory_for_planner(
            question=question,
            user_id=state.get("user_id") or state.get("thread_id"),
            datasource_id=str(state.get("datasource_id") or ""),
            project_id=state.get("project_id"),
        )
    except Exception as exc:
        logger.warning("Failed to retrieve memory context for model: %s", exc)
        return ""
