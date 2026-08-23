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
from dlcs.dbfox_data.backend.resource_kind import DATABASE_RESOURCE_KIND


def build_tool_scope_context(
    db: Session,
    request: Any,
    tool: BaseTool[Any, Any],
    resolver: CompositeResourceResolver | None = None,
) -> tuple[tuple[ResourceScopeRef, ...], dict[ResourceKey, Any]]:
    scope_refs: list[ResourceScopeRef] = []

    if resolver is None:
        from engine.runtime_composition import build_attempt_resource_resolver

        resolver = build_attempt_resource_resolver(metadata_session=db)

    frozen_refs = tuple(getattr(request, "frozen_resource_refs", None) or ())

    # Frozen input refs are the sole execution-authority source. Missing and
    # explicit-empty refs are intentionally equivalent and never derive access
    # from datasource compatibility fields or UI focus.
    for kind in tool.execution.required_resource_kinds:
        refs_for_kind = tuple(r for r in frozen_refs if r.kind == kind)
        if not refs_for_kind:
            if kind == DATABASE_RESOURCE_KIND:
                raise ToolInputError("此工具需要数据库资源，但请求中没有授权的数据库。")
            if kind == "workspace":
                raise ToolInputError("当前项目没有已授权的本地工作目录。")
            raise ToolInputError(f"此工具需要 {kind} 资源，但请求中未授权。")
        scope_refs.extend(refs_for_kind)

    try:
        resources = resolver.resolve(tuple(scope_refs))
    except ValueError as exc:
        raise ToolInputError("当前项目工作目录不可用。") from exc
    except KeyError as exc:
        raise ToolInputError(f"此工具需要 {exc} 资源，但未配置解析器。") from exc

    return tuple(scope_refs), resources
