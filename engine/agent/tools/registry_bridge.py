from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from engine.agent_core.tool_registry import ToolRegistry, tool_to_group
from engine.agent.tools.tool_manifest import enrich_description
from engine.agent.tools.tool_aliases import to_alias

logger = logging.getLogger("databox.databox_agent.tools.registry_bridge")


class EmptyToolInput(BaseModel):
    pass


def _model_from_schema(tool_name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Build a Pydantic model from a JSON Schema dict for tool input validation.

    Handles the common case: ``{"type": "object", "properties": {...}, "required": [...]}``
    so that YAML-registered tools have model-visible args_schema even without
    a hand-written input_model.
    """
    from pydantic import create_model

    properties = schema.get("properties") or {}
    required: set[str] = set(schema.get("required") or [])
    fields: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        py_type = _json_type_to_python(prop_schema)
        default = ... if prop_name in required else None
        description = prop_schema.get("description", "")
        fields[prop_name] = (py_type, Field(default=default, description=description))

    model_name = f"Dynamic_{tool_name.replace('.', '_')}"
    return create_model(model_name, **fields)  # type: ignore[call-overload]


def _json_type_to_python(schema: dict[str, Any]) -> type:
    """Map a basic JSON Schema type to a Python type for Pydantic fields."""
    type_map: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    type_str = schema.get("type", "string")
    return type_map.get(type_str, str)


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

        # Prefer spec.input_model (Pydantic), then derive from spec.input_schema (YAML/dict),
        # fall back to EmptyToolInput so the model sees the correct parameters.
        input_model = spec.input_model
        if input_model is None and isinstance(spec.input_schema, dict) and spec.input_schema.get("properties"):
            input_model = _model_from_schema(spec.name, spec.input_schema)
        if input_model is None:
            input_model = EmptyToolInput

        # Use spec.group if available, fall back to static mapping
        group = spec.group or tool_to_group(spec.name)

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
