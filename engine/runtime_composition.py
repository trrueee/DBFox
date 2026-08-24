"""Runtime composition root assembling built-in and active DLC product capabilities.

This module is the backend product-composition root. It compiles built-in and
activated DLC contributions into an immutable RuntimeContributionSnapshot, and
materializes that snapshot into standard ToolRegistry, CompositeResourceResolver,
and RunLoop instances without any domain DLC branches in Kernel code.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


from engine.agent.completion import CompletionPolicy
from engine.agent.context_fragment import ContextContributor
from engine.agent.resource_refs import (
    ProjectResourceDescriptor,
    ProjectResourceProvider,
    RequestedResourceRef,
)
from engine.db import SessionLocal
from engine.dlc.compiler import ContributionCompiler, platform_builtin_contributions
from engine.dlc.system_bundle import (
    bootstrap_system_dlcs,
    embedded_system_dlc_manifest_path,
    load_system_dlc_bundle_manifest,
)
from engine.dlc.snapshot import (
    CapabilityGuidanceContribution,
    ResourceResolverContribution,
    RuntimeContributionSnapshot,
)
from engine.dlc.trust import DlcTrustStore
from engine.resource import ResourceScopeRef
from engine.runtime_paths import private_runtime_dir
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.attempt import CompositeResourceResolver, ScopedResourceResolver



if TYPE_CHECKING:
    from engine.agent.loop import RunLoop

_ACTIVE_RUNTIME_SNAPSHOT: RuntimeContributionSnapshot | None = None

def active_runtime_snapshot() -> RuntimeContributionSnapshot | None:
    """Return the installed snapshot without triggering runtime initialization."""

    return _ACTIVE_RUNTIME_SNAPSHOT


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
    system_dlc_dir: Path | None = None,
    system_dlc_manifest: Path | None = None,
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

    resolved_system_dlc_dir = system_dlc_dir
    if resolved_system_dlc_dir is None:
        configured_system_dlc_dir = os.environ.get("DBFOX_SYSTEM_DLC_DIR", "").strip()
        if configured_system_dlc_dir:
            resolved_system_dlc_dir = Path(configured_system_dlc_dir)

    if system_dlc_manifest is None:
        configured_manifest = os.environ.get("DBFOX_SYSTEM_DLC_MANIFEST", "").strip()
        if configured_manifest:
            system_dlc_manifest = Path(configured_manifest)

    compiler_trust_store = trust_store
    if resolved_system_dlc_dir is not None:
        manifest_path = system_dlc_manifest or embedded_system_dlc_manifest_path()
        bootstrap_result = bootstrap_system_dlcs(
            resolved_storage,
            resolved_system_dlc_dir,
            manifest_path=manifest_path,
        )
        official = load_system_dlc_bundle_manifest(manifest_path)
        trusted_keys = compiler_trust_store.load() if compiler_trust_store else {}
        trusted_keys[bootstrap_result.publisher_key_id] = (
            official.publisher_public_key
        )
        compiler_trust_store = DlcTrustStore(
            trusted_keys=trusted_keys,
            storage_root=resolved_storage,
        )
    compiler = ContributionCompiler(
        resolved_storage,
        trust_store=compiler_trust_store,
        developer_mode=developer_mode,
    )
    if resolved_system_dlc_dir is None:
        logger.warning(
            "System DLC bundle is unavailable; starting with the capability-neutral "
            "Kernel only"
        )
    snapshot = compiler.compile(built_ins=platform_builtin_contributions())
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
            provider_name=tool_contrib.provider_name,
        )
    return registry.freeze()


def default_project_resource_providers(
    snapshot: RuntimeContributionSnapshot | None = None,
) -> tuple[ProjectResourceProvider, ...]:
    """Return all active resource discovery providers from snapshot."""
    snap = snapshot or get_active_runtime_snapshot()
    return snap.resource_providers


def default_capability_guidance(
    snapshot: RuntimeContributionSnapshot | None = None,
) -> tuple[CapabilityGuidanceContribution, ...]:
    return (snapshot or get_active_runtime_snapshot()).capability_guidance


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

    # Absence of an explicit request never grants Project resources.
    return ()


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


def default_credential_reference_probes(
    snapshot: RuntimeContributionSnapshot | None = None,
) -> dict[str, Callable[[Session, frozenset[str]], bool]]:
    """Return capability-owned read-only probes for credential lease recovery."""

    snap = snapshot or get_active_runtime_snapshot()
    return {item.owner_id: item.probe for item in snap.credential_reference_probes}


def build_default_completion_policy(
    snapshot: RuntimeContributionSnapshot | None = None,
) -> CompletionPolicy:
    """Compose completion semantics from the immutable Runtime snapshot."""
    snap = snapshot or get_active_runtime_snapshot()
    return CompletionPolicy(
        constraints=tuple(item.constraint for item in snap.completion_constraints),
        supports=tuple(item.support for item in snap.completion_supports),
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
        capability_guidance=default_capability_guidance(snap),
        completion=CompletionGate(build_default_completion_policy(snap)),
    )
