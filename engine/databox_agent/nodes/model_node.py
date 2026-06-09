from __future__ import annotations

from typing import Any
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from engine.databox_agent.model.model_factory import get_chat_model
from engine.databox_agent.model.system_prompt import build_system_prompt
from engine.databox_agent.model.context_builder import build_context_message
from engine.databox_agent.tools.langchain_tools import build_langchain_tools
from engine.databox_agent.graph.state import DataBoxAgentState


def call_model(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable") or {}
    model_name = configurable.get("model_name")
    api_key = configurable.get("api_key")
    api_base = configurable.get("api_base")
    registry = configurable.get("registry")

    tools = build_langchain_tools(registry)

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
