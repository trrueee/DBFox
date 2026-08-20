"""Contribution compiler assembling built-in and active DLC contributions into RuntimeContributionSnapshot."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from typing import Any

from sqlalchemy.orm import Session

from engine.agent.artifact import (
    _KNOWN_ARTIFACT_TYPES,
    artifact_payload_contracts,
    register_artifact_payload_contract,
)
from engine.agent.context_fragment import ContextContributor
from engine.agent.resource_refs import ProjectResourceProvider
from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.host import DefaultBackendExtensionHost, StagedDlcContributions
from engine.dlc.loader import (
    derive_dlc_namespace,
    load_dlc_backend,
    purge_dlc_namespace,
    reverify_installed_package,
)
from engine.dlc.manifest import DlcManifest
from engine.dlc.registry import InstalledDlcRecord, InstalledDlcRegistry
from engine.dlc.snapshot import (
    ActivatedDlcIdentity,
    ArtifactContractContribution,
    DlcOperationContribution,
    ResourceResolverContribution,
    RuntimeContributionSnapshot,
    ToolContribution,
    compute_snapshot_id,
)
from engine.dlc.trust import DlcTrustStore
from engine.tools.runtime.base import BaseTool, ToolCapability

logger = logging.getLogger(__name__)

# Capabilities supported for installable in-process DLC Tools in v1
SUPPORTED_DLC_CAPABILITIES: frozenset[ToolCapability] = frozenset(
    {
        "network",
        "filesystem_read",
        "filesystem_write",
    }
)


def _check_tool_permissions(manifest: DlcManifest, tool: BaseTool[Any, Any]) -> None:
    """Validate that tool capabilities are covered by manifest permission scopes."""
    capabilities = set(tool.execution.capabilities)
    for cap in capabilities:
        if cap not in SUPPORTED_DLC_CAPABILITIES:
            raise DlcError(
                DlcErrorCode.PERMISSION_VIOLATION,
                f"Tool '{tool.name}' requested unsupported capability '{cap}' for DLC '{manifest.id}'. "
                "Installable DLCs in v1 may only request 'network', 'filesystem_read', or 'filesystem_write'.",
            )
        # Check that manifest declares covering permission
        has_permission = False
        for perm in manifest.permissions:
            perm_base = perm.split(":", 1)[0]
            if perm_base == cap:
                has_permission = True
                break
        if not has_permission:
            raise DlcError(
                DlcErrorCode.PERMISSION_VIOLATION,
                f"Tool '{tool.name}' requires capability '{cap}', but DLC '{manifest.id}' does not declare permission '{cap}' in manifest.json",
            )


class ContributionCompiler:
    """Compiles built-in product contributions and enabled DLCs into a frozen RuntimeContributionSnapshot."""

    def __init__(
        self,
        storage_root: Path,
        *,
        trust_store: DlcTrustStore | None = None,
        developer_mode: bool = False,
    ) -> None:
        self.storage_root = storage_root
        self.trust_store = trust_store or DlcTrustStore()
        self.developer_mode = developer_mode
        self.registry = InstalledDlcRegistry(storage_root)

    def compile(
        self,
        *,
        built_in_tools: Sequence[ToolContribution | BaseTool[Any, Any]] | None = None,
        built_in_resource_providers: Sequence[ProjectResourceProvider] | None = None,
        built_in_resource_resolvers: Sequence[tuple[str, Any] | ResourceResolverContribution] | None = None,
        built_in_context_contributors: Sequence[Callable[[Session], ContextContributor]] | None = None,
    ) -> RuntimeContributionSnapshot:
        """Execute the full compilation pipeline and return an immutable RuntimeContributionSnapshot."""
        # 1. Load registry records
        try:
            self.registry.load()
            records = self.registry.list_installed_dlcs()
        except Exception as exc:
            logger.warning(f"Failed to load InstalledDlcRegistry: {exc}; proceeding with built-ins only.")
            records = []

        # 2. Filter enabled DLCs and sort canonically by dlc_id
        enabled_records: list[InstalledDlcRecord] = [
            r for r in records if r.desired_enabled and r.selected_digest
        ]
        enabled_records.sort(key=lambda r: r.dlc_id)

        # 3. Resolve built-in contributions
        if built_in_tools is None:
            from engine.tools.builtin.registry import (
                register_conversation_functions,
                register_core_functions,
                register_data_extension,
                register_remote_job_extension,
                register_workspace_extension,
                register_workspace_write_extension,
            )
            from engine.github.tools import register_github_extension
            from engine.tools.runtime import ToolRegistry

            temp_reg = ToolRegistry(available_backends=frozenset({"in_process", "isolated_process"}))
            register_core_functions(temp_reg)
            register_conversation_functions(temp_reg)
            register_data_extension(temp_reg)
            register_workspace_extension(temp_reg)
            register_workspace_write_extension(temp_reg)
            register_remote_job_extension(temp_reg)
            register_github_extension(temp_reg)
            resolved_built_in_tools: list[ToolContribution] = [
                ToolContribution(
                    tool=temp_reg.require(name),  # type: ignore[arg-type]
                    owner_id=temp_reg.owner_of(name) or "dbfox.builtin",
                    package_digest=None,
                )
                for name in temp_reg.tool_names()
            ]
        else:
            resolved_built_in_tools = [
                t if isinstance(t, ToolContribution)
                else ToolContribution(tool=t, owner_id="dbfox.builtin", package_digest=None)
                for t in built_in_tools
            ]

        if built_in_resource_providers is None:
            from engine.github.resource import list_github_resources
            from engine.runtime_composition import (
                list_database_resources,
                list_workspace_resources,
            )
            resolved_providers: list[ProjectResourceProvider] = [
                list_database_resources,
                list_workspace_resources,
                list_github_resources,
            ]
        else:
            resolved_providers = list(built_in_resource_providers)


        if built_in_resource_resolvers is None:
            from engine.db import SessionLocal
            from engine.github.resource import resolve_github_repository
            from engine.tools.runtime.resource_context import resolve_workspace_resource

            resolved_resolvers: list[ResourceResolverContribution] = [
                ResourceResolverContribution(kind="database", resolver=lambda ref: SessionLocal(), owner_id="dbfox.builtin"),
                ResourceResolverContribution(kind="workspace", resolver=lambda ref: resolve_workspace_resource(SessionLocal(), ref), owner_id="dbfox.builtin"),
                ResourceResolverContribution(kind="github.repository", resolver=lambda ref: resolve_github_repository(SessionLocal(), ref), owner_id="dbfox.builtin"),
            ]
        else:
            resolved_resolvers = [
                r if isinstance(r, ResourceResolverContribution)
                else ResourceResolverContribution(kind=r[0], resolver=r[1], owner_id="dbfox.builtin")
                for r in built_in_resource_resolvers
            ]

        if built_in_context_contributors is None:
            from engine.agent.workspace_context import WorkspaceContextContributor
            from engine.github.context import GitHubContextContributor

            resolved_context: list[Callable[[Session], ContextContributor]] = [
                WorkspaceContextContributor,
                GitHubContextContributor,
            ]
        else:
            resolved_context = list(built_in_context_contributors)

        # 4. Track existing identifiers to detect conflicts
        known_tool_names: set[str] = {tc.tool.name for tc in resolved_built_in_tools}
        known_resolver_kinds: set[str] = {rc.kind for rc in resolved_resolvers}
        known_artifact_types: set[str] = set(_KNOWN_ARTIFACT_TYPES) | {
            t for t, _ in artifact_payload_contracts.snapshot().keys()
        }
        known_operations: set[tuple[str, str]] = set()

        active_dlcs: list[ActivatedDlcIdentity] = []
        all_tools: list[ToolContribution] = list(resolved_built_in_tools)
        all_resource_providers: list[ProjectResourceProvider] = list(resolved_providers)
        all_resource_resolvers: list[ResourceResolverContribution] = list(resolved_resolvers)
        all_context_contributors: list[Callable[[Session], ContextContributor]] = list(resolved_context)
        all_artifact_contracts: list[ArtifactContractContribution] = []
        all_operations: list[DlcOperationContribution] = []


        # 4. Activate each enabled DLC in canonical order with isolation
        for record in enabled_records:
            dlc_id = record.dlc_id
            selected_digest = record.selected_digest
            if not selected_digest:
                continue

            namespace = derive_dlc_namespace(dlc_id, selected_digest)
            try:
                # Pre-verification
                manifest, package_root, trust_status, key_fingerprint = reverify_installed_package(
                    dlc_id,
                    selected_digest,
                    self.storage_root,
                    self.trust_store,
                    developer_mode=self.developer_mode,
                )

                # Skip backend loading if no backend entrypoint declared
                if not manifest.entrypoints.backend:
                    active_dlcs.append(
                        ActivatedDlcIdentity(
                            dlc_id=dlc_id,
                            package_version=manifest.version,
                            package_digest=selected_digest,
                            publisher_key_id=key_fingerprint,
                            trust_status=trust_status,
                            frontend_entrypoint=manifest.entrypoints.frontend,
                        )
                    )
                    continue

                # Load backend module
                register_func = load_dlc_backend(package_root, manifest, selected_digest)

                # Staging execution
                staging = StagedDlcContributions(
                    dlc_id=dlc_id,
                    package_digest=selected_digest,
                    manifest=manifest,
                )
                host = DefaultBackendExtensionHost(staging)
                register_func(host)

                # Validate staged contributions
                for tool in staging.tools:
                    _check_tool_permissions(manifest, tool)
                    if tool.name in known_tool_names:
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Tool '{tool.name}' from DLC '{dlc_id}' conflicts with an existing registered tool",
                        )

                for kind, _ in staging.resource_resolvers:
                    if kind in known_resolver_kinds:
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Resource resolver kind '{kind}' from DLC '{dlc_id}' conflicts with an existing resolver",
                        )

                for art_type, schema_ver, _ in staging.artifact_contracts:
                    if art_type in known_artifact_types:
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Artifact type '{art_type}' from DLC '{dlc_id}' conflicts with an existing artifact type",
                        )

                for op_spec in staging.operations:
                    op_key = (dlc_id, op_spec.name)
                    if op_key in known_operations:
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Operation '{op_spec.name}' from DLC '{dlc_id}' is already registered",
                        )

                # Commit staged contributions
                for tool in staging.tools:
                    known_tool_names.add(tool.name)
                    all_tools.append(
                        ToolContribution(tool=tool, owner_id=dlc_id, package_digest=selected_digest)
                    )

                all_resource_providers.extend(staging.resource_providers)

                for kind, resolver in staging.resource_resolvers:
                    known_resolver_kinds.add(kind)
                    all_resource_resolvers.append(
                        ResourceResolverContribution(kind=kind, resolver=resolver, owner_id=dlc_id)
                    )

                all_context_contributors.extend(staging.context_contributors)

                for art_type, schema_ver, validator in staging.artifact_contracts:
                    known_artifact_types.add(art_type)
                    all_artifact_contracts.append(
                        ArtifactContractContribution(
                            artifact_type=art_type,
                            schema_version=schema_ver,
                            validator=validator,
                            owner_id=dlc_id,
                        )
                    )

                for op_spec in staging.operations:
                    known_operations.add((dlc_id, op_spec.name))
                    all_operations.append(
                        DlcOperationContribution(dlc_id=dlc_id, spec=op_spec)
                    )

                active_dlcs.append(
                    ActivatedDlcIdentity(
                        dlc_id=dlc_id,
                        package_version=manifest.version,
                        package_digest=selected_digest,
                        publisher_key_id=key_fingerprint,
                        trust_status=trust_status,
                        frontend_entrypoint=manifest.entrypoints.frontend,
                    )
                )

            except Exception as exc:
                logger.error(f"Failed to activate DLC '{dlc_id}': {exc}", exc_info=True)
                purge_dlc_namespace(namespace)
                # Broken DLC isolation: do not fail entire runtime

        # 5. Atomically register accepted artifact payload contracts
        for art_contrib in all_artifact_contracts:
            if artifact_payload_contracts.get(art_contrib.artifact_type, art_contrib.schema_version) is None:
                try:
                    register_artifact_payload_contract(
                        art_contrib.artifact_type,
                        art_contrib.schema_version,
                        art_contrib.validator,
                    )
                except Exception as exc:
                    logger.warning(
                        f"Failed to register artifact payload contract for '{art_contrib.artifact_type}': {exc}"
                    )


        # 6. Compute deterministic snapshot ID
        active_dlc_tuple = tuple(active_dlcs)
        snapshot_id = compute_snapshot_id(active_dlc_tuple)

        return RuntimeContributionSnapshot(
            snapshot_id=snapshot_id,
            active_dlcs=active_dlc_tuple,
            tools=tuple(all_tools),
            resource_providers=tuple(all_resource_providers),
            resource_resolvers=tuple(all_resource_resolvers),
            context_contributors=tuple(all_context_contributors),
            artifact_contracts=tuple(all_artifact_contracts),
            operations=tuple(all_operations),
        )
