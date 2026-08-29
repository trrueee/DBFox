"""Build a tool's execution scope from frozen ResourceRefs."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from engine.errors import ToolInputError
from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ResourceKey,
    ResourceScopeRef,
)
from engine.tools.runtime.base import BaseTool


def build_tool_scope_context(
    db: Session,
    request: Any,
    tool: BaseTool[Any, Any],
    resolver: CompositeResourceResolver,
) -> tuple[tuple[ResourceScopeRef, ...], dict[ResourceKey, Any]]:
    scope_refs: list[ResourceScopeRef] = []

    frozen_refs = tuple(getattr(request, "frozen_resource_refs", None) or ())

    # ToolRequest carries the exact refs frozen on this Invocation. Missing and
    # explicit-empty refs are equivalent; resolution never expands from Project
    # discovery metadata, domain compatibility fields, or UI focus.
    for requirement in tool.execution.required_resources:
        kind = requirement.kind
        refs_for_kind = tuple(r for r in frozen_refs if r.kind == kind)
        if not refs_for_kind:
            raise ToolInputError(f"此工具需要 {kind} 资源，但请求中未授权。")
        scope_refs.extend(refs_for_kind)

    try:
        resources = resolver.resolve(tuple(scope_refs))
    except ValueError as exc:
        raise ToolInputError("授权资源当前不可用。") from exc
    except KeyError as exc:
        raise ToolInputError(f"此工具需要 {exc} 资源，但未配置解析器。") from exc

    return tuple(scope_refs), resources
