from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel
from langchain_core.tools import StructuredTool

from engine.agent_kernel.tool_registry import ToolRegistry

logger = logging.getLogger("databox.databox_agent.tools.registry_bridge")


class EmptyToolInput(BaseModel):
    pass


def make_dummy_func(name: str):
    """Return a dummy function for LangChain StructuredTool instantiation."""
    def func(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "success", "message": f"StructuredTool wrapper for {name} invoked."}
    return func


def build_langchain_tools(registry: ToolRegistry | None) -> list[StructuredTool]:
    """Convert RegisteredTool specs from ToolRegistry to LangChain StructuredTool instances."""
    if registry is None:
        return []

    tools = []
    for spec in registry.list_specs():
        input_model = spec.input_model or EmptyToolInput
        tool = StructuredTool.from_function(
            name=spec.name,
            description=spec.description,
            args_schema=input_model,
            func=make_dummy_func(spec.name),
        )
        tools.append(tool)
    return tools
