from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel
from langchain_core.tools import StructuredTool

from engine.agent_core.tool_registry import ToolRegistry, tool_to_group
from engine.agent.tools.tool_manifest import enrich_description
from engine.agent.tools.tool_aliases import to_alias

logger = logging.getLogger("databox.databox_agent.tools.registry_bridge")


class EmptyToolInput(BaseModel):
    pass


def make_dummy_func(name: str):
    """Return a dummy function for LangChain StructuredTool instantiation.

    The actual execution is handled by execute_allowed_tools() in tool_node.py.
    This function exists only so LangChain's bind_tools() has a callable to wrap.
    """
    def func(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "success", "message": f"StructuredTool wrapper for {name} invoked."}
    return func


def build_langchain_tools(
    registry: ToolRegistry | None,
    allowed_groups: list[str] | None = None,
) -> list[StructuredTool]:
    """Convert RegisteredTool specs from ToolRegistry to LangChain StructuredTool instances.

    Uses enriched descriptions from tool_manifest.py so the LLM gets
    DataBox-specific affordance hints (when to use, what the tool produces,
    what it depends on).

    When allowed_groups is non-empty, only tools whose group matches one of
    the entries are included.  An empty list means "no tools at all".
    A None value (default) means "all tools" (backward-compatible).
    """
    if registry is None:
        return []

    tools = []
    for spec in registry.list_specs():
        # Filter by allowed tool groups when specified
        if allowed_groups is not None:
            group = tool_to_group(spec.name)
            if group is None or group not in allowed_groups:
                continue

        input_model = spec.input_model or EmptyToolInput
        description = enrich_description(spec.name, spec.description)
        alias = to_alias(spec.name)
        tool = StructuredTool.from_function(
            name=alias,
            description=description,
            args_schema=input_model,
            func=make_dummy_func(spec.name),
        )
        tools.append(tool)
    return tools
