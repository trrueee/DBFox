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


def build_tool_scope_context(
    db: Session,
    request: Any,
    tool: BaseTool[Any, Any],
) -> tuple[tuple[ResourceScopeRef, ...], dict[str, Any]]:
    scope_refs = [
        ResourceScopeRef(
            kind="database",
            id=str(getattr(request, "datasource_id", "")),
            version=int(getattr(request, "datasource_generation", 0) or 0),
        )
    ]
    resources: dict[str, Any] = {}

    if "filesystem_read" in tool.execution.capabilities:
        datasource = db.get(DataSource, scope_refs[0].id)
        project_id = str(datasource.project_id) if datasource and datasource.project_id else ""
        project = db.get(Project, project_id) if project_id else None
        workspace_root = str(project.workspace_root or "").strip() if project else ""
        if not workspace_root:
            raise ToolInputError(
                "当前项目没有已授权的本地工作目录。"
            )
        try:
            workspace = WorkspaceReadService(workspace_root)
        except WorkspaceReadError as exc:
            raise ToolInputError(
                "当前项目工作目录不可用。"
            ) from exc
        root_digest = hashlib.sha256(
            str(workspace.root).encode("utf-8")
        ).hexdigest()[:16]
        scope_refs.append(
            ResourceScopeRef(
                kind="workspace",
                id=project_id,
                version=root_digest,
            )
        )
        resources["workspace"] = workspace

    return tuple(scope_refs), resources
