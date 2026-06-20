from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from engine.tools.runtime.aliases import to_alias
from engine.tools.runtime.registry import ToolRegistry


class EmptyToolInput(BaseModel):
    pass


def _dummy_func(name: str):
    def func(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "success", "message": f"StructuredTool wrapper for {name} invoked."}

    return func


def build_langchain_tools(
    registry: ToolRegistry | None,
    allowed_groups: list[str] | None = None,
) -> list[StructuredTool]:
    if registry is None:
        return []

    tools: list[StructuredTool] = []
    for tool in registry.list_tools():
        spec = tool.spec
        if not spec.policy.visible_to_model:
            continue
        if allowed_groups is not None and spec.group not in allowed_groups:
            continue
        alias = to_alias(spec.name)
        if alias == spec.name:
            alias = spec.name.replace(".", "_")
        input_model = spec.input_model or EmptyToolInput
        tools.append(
            StructuredTool.from_function(
                name=alias,
                description=spec.description,
                args_schema=input_model,
                func=_dummy_func(spec.name),
            )
        )
    return tools
