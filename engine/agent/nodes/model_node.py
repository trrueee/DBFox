from __future__ import annotations

from typing import Any
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from engine.agent.model.model_factory import get_chat_model
from engine.agent.model.system_prompt import build_system_prompt
from engine.agent.model.context_builder import build_context_message
from engine.agent.tools.langchain_tools import build_langchain_tools
from engine.agent.graph.state import DataBoxAgentState


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

    configurable = config.get("configurable") or {}
    model_name = configurable.get("model_name")
    api_key = configurable.get("api_key")
    api_base = configurable.get("api_base")
    registry = configurable.get("registry")

    allowed_groups = state.get("allowed_tool_groups") or []
    # None (not []) means "all tools" for backward compatibility
    tools = build_langchain_tools(registry, allowed_groups=allowed_groups if allowed_groups else None)

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
