"""Runtime composition root assembling built-in and active DLC product capabilities.

This module is the backend product-composition root. It compiles built-in and
activated DLC contributions into an immutable RuntimeContributionSnapshot, and
materializes that snapshot into standard ToolRegistry, CompositeResourceResolver,
and RunLoop instances without any domain DLC branches in Kernel code.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


from engine.agent.completion import CompletionPolicy
from engine.agent.completion_data import DataCompletionSupport, DataResultCitationConstraint
from engine.agent.context_fragment import ContextContributor
from engine.agent.resource_refs import (
    ProjectResourceDescriptor,
    ProjectResourceProvider,
    RequestedResourceRef,
)
from engine.db import SessionLocal
from engine.dlc.compiler import ContributionCompiler
from engine.dlc.snapshot import (
    ResourceResolverContribution,
    RuntimeContributionSnapshot,
)
from engine.dlc.trust import DlcTrustStore
from engine.models import DataSource, Project
from engine.runtime_paths import private_runtime_dir
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ResourceScopeRef,
    ScopedResourceResolver,
)
from engine.tools.runtime.resource_context import (
    resolve_workspace_scope_ref,
)



if TYPE_CHECKING:
    from engine.agent.loop import RunLoop

_ACTIVE_RUNTIME_SNAPSHOT: RuntimeContributionSnapshot | None = None


def get_active_runtime_snapshot() -> RuntimeContributionSnapshot:
    """Return the active in-memory RuntimeContributionSnapshot for the running process."""
    global _ACTIVE_RUNTIME_SNAPSHOT
    if _ACTIVE_RUNTIME_SNAPSHOT is None:
        _ACTIVE_RUNTIME_SNAPSHOT = initialize_runtime_snapshot()
    return _ACTIVE_RUNTIME_SNAPSHOT


def set_active_runtime_snapshot(snapshot: RuntimeContributionSnapshot | None) -> None:
    """Explicitly set the active RuntimeContributionSnapshot (for testing or lifecycle restart)."""
    global _ACTIVE_RUNTIME_SNAPSHOT
    _ACTIVE_RUNTIME_SNAPSHOT = snapshot



def initialize_runtime_snapshot(
    storage_root: Path | None = None,
    *,
    trust_store: DlcTrustStore | None = None,
    developer_mode: bool = False,
) -> RuntimeContributionSnapshot:
    """Build the frozen RuntimeContributionSnapshot from built-in contributions and enabled DLCs."""
    if storage_root is None:
        try:
            resolved_storage = private_runtime_dir("dlcs")
        except Exception as exc:
            logger.error("Failed to establish private runtime directory for DLCs: %s", exc)
            # Fail closed without scanning CWD
            empty_path = Path(tempfile.gettempdir()) / "dbfox_empty_dlc_storage"
            compiler = ContributionCompiler(
                empty_path,
                trust_store=trust_store,
                developer_mode=developer_mode,
            )
            snapshot = compiler.compile()
            set_active_runtime_snapshot(snapshot)
            return snapshot
    else:
        resolved_storage = storage_root


    compiler = ContributionCompiler(
        resolved_storage,
        trust_store=trust_store,
        developer_mode=developer_mode,
    )
    snapshot = compiler.compile()
    set_active_runtime_snapshot(snapshot)
    return snapshot



def build_product_tool_registry(
    snapshot: RuntimeContributionSnapshot | None = None,
) -> ToolRegistry:
    """Build the complete frozen Tool Registry for the DBFox product from snapshot."""
    snap = snapshot or get_active_runtime_snapshot()
    registry = ToolRegistry(
        available_backends=frozenset({"in_process", "isolated_process"})
    )
    for tool_contrib in snap.tools:
        registry.register(
            tool_contrib.tool,
            owner=tool_contrib.owner_id,
            package_digest=tool_contrib.package_digest,
        )
    return registry.freeze()


# ---------------------------------------------------------------------------
# Project Resource Providers (Discovery)
# ---------------------------------------------------------------------------


def list_database_resources(db: Session, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
    """Discover database resources (DataSources) belonging to a project."""
    if db is None or not project_id:
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
    if db is None or not project_id:
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


def default_project_resource_providers(
    snapshot: RuntimeContributionSnapshot | None = None,
) -> tuple[ProjectResourceProvider, ...]:
    """Return all active resource discovery providers from snapshot."""
    snap = snapshot or get_active_runtime_snapshot()
    return snap.resource_providers


def discover_project_resources(
    db: Session,
    project_id: str,
    snapshot: RuntimeContributionSnapshot | None = None,
) -> tuple[ProjectResourceDescriptor, ...]:
    """Discover all available resources across all registered providers for a project."""
    snap = snapshot or get_active_runtime_snapshot()
    descriptors: list[ProjectResourceDescriptor] = []
    seen: set[tuple[str, str]] = set()
    for provider in snap.resource_providers:
        for d in provider(db, project_id):
            key = (d.kind, d.id)
            if key in seen:
                raise ValueError(f"Duplicate resource discovery identity (kind={d.kind!r}, id={d.id!r})")
            seen.add(key)
            descriptors.append(d)
    return tuple(descriptors)


def authorize_project_resources(
    db: Session,
    project_id: str,
    requested: Sequence[RequestedResourceRef] | None,
    fallback_datasource_id: str | None = None,
    snapshot: RuntimeContributionSnapshot | None = None,
) -> tuple[ResourceScopeRef, ...]:
    """Authorize requested resources against project discovery, attaching server canonical versions."""
    if requested is not None:
        available = {
            (d.kind, d.id): d
            for d in discover_project_resources(db, project_id, snapshot=snapshot)
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
def _adapt_scoped_resolver(
    contrib: ResourceResolverContribution,
    metadata_session: Session | None = None,
) -> ScopedResourceResolver:
    """Adapt a ResourceResolverContribution into a standard ScopedResourceResolver based on typed platform binding."""
    if contrib.binding == "metadata_session":
        resolver = contrib.resolver

        def _session_wrapped(ref: ResourceScopeRef) -> Any:
            if metadata_session is not None:
                return resolver(metadata_session, ref)
            with SessionLocal() as db:
                return resolver(db, ref)

        return cast(ScopedResourceResolver, _session_wrapped)

    # scope_only (DLCs and neutral resolvers): strictly receives ref only, never receives Session
    return cast(ScopedResourceResolver, contrib.resolver)


def build_attempt_resource_resolver(
    metadata_session: Session | None = None,
    snapshot: RuntimeContributionSnapshot | None = None,
) -> CompositeResourceResolver:
    """Build composite attempt resolver from snapshot with attempt-scoped metadata session."""
    snap = snapshot or get_active_runtime_snapshot()
    resolver = CompositeResourceResolver()

    for res_contrib in snap.resource_resolvers:
        resolver.register(
            res_contrib.kind,
            _adapt_scoped_resolver(res_contrib, metadata_session),
        )

    return resolver.freeze()


def default_context_contributors(
    snapshot: RuntimeContributionSnapshot | None = None,
) -> tuple[Callable[[Session], ContextContributor], ...]:
    """Return all active context contributors from snapshot."""
    snap = snapshot or get_active_runtime_snapshot()
    return snap.context_contributors


def build_default_completion_policy() -> CompletionPolicy:
    """Compose the current Data completion contributions for DBFox."""
    return CompletionPolicy(
        constraints=(DataResultCitationConstraint(),),
        support=DataCompletionSupport(),
    )


def build_product_run_loop(
    *,
    session_factory: Callable[[], Session],
    snapshot: RuntimeContributionSnapshot | None = None,
) -> RunLoop:
    """Construct the production RunLoop with explicit product contributions from snapshot."""
    from engine.agent.completion import CompletionGate
    from engine.agent.loop import RunLoop

    snap = snapshot or get_active_runtime_snapshot()
    return RunLoop(
        session_factory=session_factory,
        registry=build_product_tool_registry(snap),
        context_contributors=default_context_contributors(snap),
        completion=CompletionGate(build_default_completion_policy()),
    )
