"""Explicit compile-time composition of DBFox's built-in product capabilities.

This module is the sole backend product-composition root.  It assembles the
existing typed Tool, resource, Context and Completion contracts without a
plugin manager, manifest, container, or additional contribution model.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.orm import Session

from engine.agent.completion import CompletionPolicy
from engine.agent.completion_data import DataCompletionSupport, DataResultCitationConstraint
from engine.agent.context_fragment import ContextContributor
from engine.agent.resource_refs import (
    ProjectResourceDescriptor,
    ProjectResourceProvider,
    RequestedResourceRef,
)
from engine.agent.workspace_context import WorkspaceContextContributor
from engine.db import SessionLocal
from engine.github.context import GitHubContextContributor
from engine.github.resource import list_github_resources, resolve_github_repository
from engine.github.tools import register_github_extension
from engine.models import DataSource, Project
from engine.tools.builtin.registry import (
    register_conversation_functions,
    register_core_functions,
    register_data_extension,
    register_remote_job_extension,
    register_workspace_extension,
    register_workspace_write_extension,
)
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ResourceScopeRef,
    ScopedResourceResolver,
)
from engine.tools.runtime.resource_context import (
    resolve_workspace_resource,
    resolve_workspace_scope_ref,
)
from engine.workspace.read_service import WorkspaceReadService

if TYPE_CHECKING:
    from engine.agent.loop import RunLoop


def build_product_tool_registry() -> ToolRegistry:
    """Build the complete frozen Tool Registry for the DBFox product."""

    registry = ToolRegistry(
        available_backends=frozenset({"in_process", "isolated_process"})
    )
    register_core_functions(registry)
    register_conversation_functions(registry)
    register_data_extension(registry)
    register_workspace_extension(registry)
    register_workspace_write_extension(registry)
    register_remote_job_extension(registry)
    register_github_extension(registry)
    return registry.freeze()


# ---------------------------------------------------------------------------
# Project Resource Providers (Discovery)
# ---------------------------------------------------------------------------


def list_database_resources(db: Session, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
    """Discover database resources (DataSources) belonging to a project."""
    if not project_id:
        return ()
    datasources = (
        db.query(DataSource)
        .filter(DataSource.project_id == project_id)
        .order_by(DataSource.created_at.asc())
        .all()
    )
    return tuple(
        ProjectResourceDescriptor(
            kind="database",
            id=str(ds.id),
            version=int(ds.connection_generation or 0),
            name=ds.name or "Database",
        )
        for ds in datasources
    )


def list_workspace_resources(db: Session, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
    """Discover workspace resource belonging to a project if configured."""
    if not project_id:
        return ()
    project = db.get(Project, project_id)
    if project is None or not project.workspace_root:
        return ()
    ref = resolve_workspace_scope_ref(db, None, project_id=project_id)
    if ref is None:
        return ()
    return (
        ProjectResourceDescriptor(
            kind="workspace",
            id=str(project.id),
            version=ref.version or "",
            name=project.name or "Workspace",
        ),
    )


def default_project_resource_providers() -> tuple[ProjectResourceProvider, ...]:
    """Return the built-in project resource discovery providers."""
    return (
        list_database_resources,
        list_workspace_resources,
        list_github_resources,
    )


def discover_project_resources(
    db: Session,
    project_id: str,
) -> tuple[ProjectResourceDescriptor, ...]:
    """Discover all available resources across all registered providers for a project."""
    descriptors: list[ProjectResourceDescriptor] = []
    for provider in default_project_resource_providers():
        descriptors.extend(provider(db, project_id))
    return tuple(descriptors)


def authorize_project_resources(
    db: Session,
    project_id: str,
    requested: Sequence[RequestedResourceRef] | None,
    fallback_datasource_id: str | None = None,
) -> tuple[ResourceScopeRef, ...]:
    """Authorize requested resources against project discovery, attaching server canonical versions."""
    if requested is not None:
        available = {
            (d.kind, d.id): d
            for d in discover_project_resources(db, project_id)
        }
        authorized: list[ResourceScopeRef] = []
        seen: set[tuple[str, str]] = set()
        for req in requested:
            key = (req.kind, req.id)
            if key not in available:
                raise ValueError(
                    f"Requested resource {req.kind}:{req.id} is not available in project {project_id}"
                )
            if key not in seen:
                seen.add(key)
                authorized.append(available[key].to_scope_ref())
        return tuple(authorized)

    # Legacy fallback path: derive from session compatibility fields
    legacy_refs: list[ResourceScopeRef] = []
    if fallback_datasource_id:
        datasource = db.get(DataSource, str(fallback_datasource_id))
        if datasource is not None:
            legacy_refs.append(
                ResourceScopeRef(
                    kind="database",
                    id=str(datasource.id),
                    version=int(datasource.connection_generation or 0),
                )
            )
            if datasource.project_id:
                ws_ref = resolve_workspace_scope_ref(db, str(datasource.id))
                if ws_ref is not None:
                    legacy_refs.append(ws_ref)
    elif project_id:
        ws_ref = resolve_workspace_scope_ref(db, None, project_id=project_id)
        if ws_ref is not None:
            legacy_refs.append(ws_ref)
    return tuple(legacy_refs)


# ---------------------------------------------------------------------------
# Attempt Resource Resolvers (Execution)
# ---------------------------------------------------------------------------


def build_attempt_resource_resolver(
    metadata_session: Session | None = None,
) -> CompositeResourceResolver:
    """Build composite attempt resolver with attempt-scoped metadata session."""

    resolver = CompositeResourceResolver()

    def resolve_database(_ref: ResourceScopeRef) -> Any:
        # In-process: leaf metadata Session; worker process: SessionLocal
        return metadata_session if metadata_session is not None else SessionLocal()

    def resolve_workspace(ref: ResourceScopeRef) -> WorkspaceReadService:
        if metadata_session is not None:
            return resolve_workspace_resource(metadata_session, ref)
        with SessionLocal() as db:
            return resolve_workspace_resource(db, ref)

    def resolve_github(ref: ResourceScopeRef) -> Any:
        if metadata_session is not None:
            return resolve_github_repository(metadata_session, ref)
        with SessionLocal() as db:
            return resolve_github_repository(db, ref)

    resolver.register("database", cast(ScopedResourceResolver, resolve_database))
    resolver.register("workspace", cast(ScopedResourceResolver, resolve_workspace))
    resolver.register("github.repository", cast(ScopedResourceResolver, resolve_github))
    return resolver.freeze()


def default_context_contributors() -> tuple[Callable[[Session], ContextContributor], ...]:
    """Return the built-in contributors; Context Kernel owns their use."""

    return (
        WorkspaceContextContributor,
        GitHubContextContributor,
    )


def build_default_completion_policy() -> CompletionPolicy:
    """Compose the current Data completion contributions for DBFox."""

    return CompletionPolicy(
        constraints=(DataResultCitationConstraint(),),
        support=DataCompletionSupport(),
    )


def build_product_run_loop(*, session_factory: Callable[[], Session]) -> RunLoop:
    """Construct the production RunLoop with explicit product contributions."""

    from engine.agent.completion import CompletionGate
    from engine.agent.loop import RunLoop

    return RunLoop(
        session_factory=session_factory,
        registry=build_product_tool_registry(),
        context_contributors=default_context_contributors(),
        completion=CompletionGate(build_default_completion_policy()),
    )
