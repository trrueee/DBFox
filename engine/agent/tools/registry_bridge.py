from __future__ import annotations

from langchain_core.tools import StructuredTool

from engine.tools.runtime.manifest import build_langchain_tools as _build_langchain_tools
from engine.tools.runtime.registry import ToolRegistry


def build_langchain_tools(
    registry: ToolRegistry | None,
    allowed_groups: list[str] | None = None,
) -> list[StructuredTool]:
    """Convert runtime BaseTool specs to model-facing StructuredTool objects."""
    return _build_langchain_tools(registry, allowed_groups=allowed_groups)
