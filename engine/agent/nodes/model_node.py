from __future__ import annotations

from typing import Any
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from engine.llm import get_chat_model
from engine.agent.model.system_prompt import build_system_prompt
from engine.agent.model.context_builder import build_context_message
from engine.agent.tools.langchain_tools import build_langchain_tools
from engine.agent.graph.state import DataBoxAgentState
from engine.agent.graph.context import graph_context


def call_model(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    # Hard block: do not invoke the model if we have already reached max_steps.
    # Without this check the model would emit one more set of tool_calls after
    # the step limit was hit, which wastes tokens and can produce confusing
    # ToolMessages for tools that will never execute.
    step_count = int(state.get("step_count", 0))
    max_steps = int(state.get("max_steps", 20))
    if step_count >= max_steps:
        if not state.get("safety"):
            err = "Agent stopped before SQL validation because max_steps was reached."
        else:
            err = f"Agent exceeded max_steps ({max_steps})."
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
        *state.get("messages", []),
    ]

    ai_msg = model_with_tools.invoke(messages)

    return {
        "messages": [ai_msg],
        "trace_events": [
            {
                "type": "agent.model.completed",
                "tool_calls": getattr(ai_msg, "tool_calls", []) or [],
            }
        ],
        "step_count": state.get("step_count", 0) + 1,
    }


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
            "Tool group you need: workspace, environment, schema, semantic, "
            "query_plan, sql_generation, sql_validation, sql_repair, execution, "
            "result, chart, answer."
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
