from __future__ import annotations

from typing import Any
from engine.agent_kernel.tool_registry import ToolRegistry


def get_tool_manifest(registry: ToolRegistry) -> list[dict[str, Any]]:
    """Return list of serialized specs for all registered tools."""
    return [spec.model_dump() for spec in registry.list_specs()]
