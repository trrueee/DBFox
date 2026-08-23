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
    BuiltinContributionSet,
    CompletionConstraintContribution,
    CompletionSupportContribution,
    CredentialReferenceProbeContribution,
    ResourceResolverContribution,
    RuntimeContributionSnapshot,
    ToolContribution,
)
from engine.dlc.trust import DlcTrustStore
from engine.resource import ResourceScopeRef
from engine.runtime_paths import private_runtime_dir
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.attempt import CompositeResourceResolver, ScopedResourceResolver



if TYPE_CHECKING:
    from engine.agent.loop import RunLoop

_ACTIVE_RUNTIME_SNAPSHOT: RuntimeContributionSnapshot | None = None


def _source_development_product_builtins() -> BuiltinContributionSet:
    """Compose the in-tree Data capability for source-only development.

    Frozen releases always supply the signed System DLC bundle. This fallback
    keeps ``python -m engine.main`` useful from a source checkout without
    weakening package verification or teaching the generic compiler about Data.
    Delete it when the development launcher bootstraps signed local packages.
    """

    from engine.tools.builtin.data_capability import (
        legacy_data_completion_constraints,
        legacy_data_completion_supports,
        legacy_data_credential_reference_probe,
        legacy_data_resource_providers,
        legacy_data_resource_resolvers,
    )
    from engine.tools.builtin.registry import register_data_extension

    platform = platform_builtin_contributions()
    registry = ToolRegistry(
        available_backends=frozenset({"in_process", "isolated_process"})
    )
    register_data_extension(registry)
    data_tools = tuple(
        ToolContribution(
            tool=registry.require(name),  # type: ignore[arg-type]
            owner_id=registry.owner_of(name) or "dbfox.data",
        )
        for name in registry.tool_names()
    )
    return BuiltinContributionSet(
        identifiers=(*platform.identifiers, "legacy.dbfox.data"),
        tools=(*platform.tools, *data_tools),
        resource_providers=legacy_data_resource_providers(),
        resource_resolvers=tuple(
            ResourceResolverContribution(
                kind=kind,
                resolver=resolver,
                owner_id="dbfox.data",
                binding=binding,
            )
            for kind, resolver, binding in legacy_data_resource_resolvers()
        ),
        completion_constraints=tuple(
            CompletionConstraintContribution(
                constraint=constraint,
                owner_id="dbfox.data",
            )
            for constraint in legacy_data_completion_constraints()
        ),
        completion_supports=tuple(
            CompletionSupportContribution(support=support, owner_id="dbfox.data")
            for support in legacy_data_completion_supports()
        ),
        credential_reference_probes=(
            CredentialReferenceProbeContribution(
                probe=legacy_data_credential_reference_probe,
                owner_id="dbfox.data",
            ),
        ),
    )


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

    compiler_trust_store = trust_store
    system_data_enabled = False
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
        from engine.dlc.registry import InstalledDlcRegistry

        data_record = InstalledDlcRegistry(resolved_storage).get_installed_dlc(
            "dbfox.data"
        )
        system_data_enabled = bool(data_record and data_record.desired_enabled)

    compiler = ContributionCompiler(
        resolved_storage,
        trust_store=compiler_trust_store,
        developer_mode=developer_mode,
    )
    if system_data_enabled:
        built_ins = platform_builtin_contributions()
    else:
        logger.warning(
            "Signed System Data DLC is unavailable or disabled; using the "
            "source-development Data composition"
        )
        built_ins = _source_development_product_builtins()
    snapshot = compiler.compile(built_ins=built_ins)
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
        completion=CompletionGate(build_default_completion_policy(snap)),
    )
