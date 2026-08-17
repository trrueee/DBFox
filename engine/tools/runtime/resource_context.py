"""Minimal Database + Workspace scope resolver used by ToolDispatcher.

This is the P5B integration point. It builds only the serializable scope refs
and the authorized resource values for the concrete tool capability; it never
injects an application container into ToolRunContext.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from engine.errors import ToolInputError
from engine.models import DataSource, Project
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.tools.runtime.base import BaseTool
from engine.workspace.read_service import WorkspaceReadError, WorkspaceReadService


class _InvocationRequestLike:
    datasource_id: str
    datasource_generation: int


_DATABASE_CAPABILITIES = frozenset(
    {"database_read", "metadata_read", "metadata_write"}
)
_WORKSPACE_CAPABILITIES = frozenset({"filesystem_read", "filesystem_write"})


def resolve_workspace_scope_ref(
    db: Session,
    datasource_id: str,
) -> ResourceScopeRef | None:
    datasource = db.get(DataSource, datasource_id)
    project_id = (
        str(datasource.project_id)
        if datasource and datasource.project_id
        else ""
    )
    project = db.get(Project, project_id) if project_id else None
    workspace_root = str(project.workspace_root or "").strip() if project else ""
    if not workspace_root:
        return None
    try:
        workspace = WorkspaceReadService(workspace_root)
    except WorkspaceReadError:
        return None
    root_digest = hashlib.sha256(
        str(workspace.root).encode("utf-8")
    ).hexdigest()[:16]
    return ResourceScopeRef(
        kind="workspace",
        id=project_id,
        version=root_digest,
        location=workspace_root,
    )


def build_tool_scope_context(
    db: Session,
    request: Any,
    tool: BaseTool[Any, Any],
) -> tuple[tuple[ResourceScopeRef, ...], dict[str, Any]]:
    capabilities = set(tool.execution.capabilities)
    scope_refs: list[ResourceScopeRef] = []
    resources: dict[str, Any] = {}

    if capabilities & _DATABASE_CAPABILITIES:
        scope_refs.append(
            ResourceScopeRef(
                kind="database",
                id=str(getattr(request, "datasource_id", "")),
                version=int(getattr(request, "datasource_generation", 0) or 0),
            )
        )
        resources["database"] = db

    if capabilities & _WORKSPACE_CAPABILITIES:
        workspace_ref = resolve_workspace_scope_ref(
            db,
            str(getattr(request, "datasource_id", "") or ""),
        )
        if workspace_ref is None:
            raise ToolInputError("当前项目没有已授权的本地工作目录。")
        scope_refs.append(workspace_ref)
        try:
            resources["workspace"] = WorkspaceReadService(workspace_ref.location or "")
        except WorkspaceReadError as exc:
            raise ToolInputError("当前项目工作目录不可用。") from exc

    return tuple(scope_refs), resources
