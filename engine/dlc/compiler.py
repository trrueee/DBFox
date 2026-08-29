"""Contribution compiler assembling built-in and active DLC contributions into RuntimeContributionSnapshot."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from engine.agent.artifact import (
    _KNOWN_ARTIFACT_TYPES,
    artifact_payload_contracts,
)
from engine.agent.context_fragment import ContextContributor
from engine.agent.resource_refs import ProjectResourceDescriptor, ProjectResourceProvider
from engine.dlc.api import (
    DlcOperationSpec,
    DlcRuntimeInfo,
    ExtensionProjectResourceProvider,
)
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
    ArtifactRepresentationContribution,
    BuiltinContributionSet,
    CompletionConstraintContribution,
    CompletionSupportContribution,
    CapabilityGuidanceContribution,
    CredentialReferenceProbeContribution,
    DlcActivationFailure,
    DlcOperationContribution,
    ResourceResolverContribution,
    RuntimeContributionSnapshot,
    ToolContribution,
    compute_snapshot_id,
)
from engine.dlc.trust import DlcTrustStore
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.base import BaseTool, ToolCapability

logger = logging.getLogger(__name__)

# Capabilities supported for installable in-process DLC Tools in v1
SUPPORTED_DLC_CAPABILITIES: frozenset[ToolCapability] = frozenset(
    {
        "network",
        "filesystem_read",
    }
)


def _owned_resource_kind(owner_id: str, kind: str) -> bool:
    return kind.startswith(f"{owner_id}.")


def _check_tool_resource_ownership(manifest: DlcManifest, tool: BaseTool[Any, Any]) -> None:
    foreign = tuple(
        requirement.kind
        for requirement in tool.execution.required_resources
        if not _owned_resource_kind(manifest.id, requirement.kind)
    )
    if foreign:
        raise DlcError(
            DlcErrorCode.PERMISSION_VIOLATION,
            f"Tool '{tool.name}' from DLC '{manifest.id}' requires foreign Resource kinds {foreign!r}. "
            "Extension API v2 permits direct resolution only for Resource kinds owned by the same DLC; "
            "cross-capability work must use Agent composition.",
        )


def _check_tool_permissions(manifest: DlcManifest, tool: BaseTool[Any, Any]) -> None:
    """Validate that tool capabilities are covered by manifest permission scopes."""
    capabilities = set(tool.execution.capabilities)
    for cap in capabilities:
        if cap not in SUPPORTED_DLC_CAPABILITIES:
            raise DlcError(
                DlcErrorCode.PERMISSION_VIOLATION,
                f"Tool '{tool.name}' requested unsupported capability '{cap}' for DLC '{manifest.id}'. "
                "Installable DLCs in v1 may only request 'network' or 'filesystem_read'.",
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


def _check_operation_permissions(manifest: DlcManifest, spec: DlcOperationSpec) -> None:
    """Validate that operation capabilities are covered by manifest permission scopes."""
    for cap in spec.capabilities:
        has_permission = False
        for perm in manifest.permissions:
            perm_base = perm.split(":", 1)[0]
            if perm_base == cap:
                has_permission = True
                break
        if not has_permission:
            raise DlcError(
                DlcErrorCode.PERMISSION_VIOLATION,
                f"Operation '{spec.name}' requires capability '{cap}', but DLC '{manifest.id}' does not declare permission '{cap}' in manifest.json",
            )


def platform_builtin_contributions() -> BuiltinContributionSet:
    """Build the Runtime-owned contribution seed without business domains."""

    from engine.tools.builtin.registry import (
        register_conversation_functions,
        register_core_functions,
        register_remote_job_extension,
    )

    registry = ToolRegistry(
        available_backends=frozenset({"in_process", "isolated_process"})
    )
    register_core_functions(registry)
    register_conversation_functions(registry)
    register_remote_job_extension(registry)
    return BuiltinContributionSet(
        identifiers=("dbfox.core", "dbfox.conversation", "dbfox.remote_job"),
        tools=tuple(
            ToolContribution(
                tool=registry.require(name),  # type: ignore[arg-type]
                owner_id=registry.owner_of(name) or "dbfox.core",
                provider_name=name,
            )
            for name in registry.tool_names()
        ),
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
        self.trust_store = trust_store or DlcTrustStore(
            storage_root=self.storage_root
        )
        self.developer_mode = developer_mode
        self.registry = InstalledDlcRegistry(storage_root)

    def compile(
        self,
        *,
        built_ins: BuiltinContributionSet | None = None,
    ) -> RuntimeContributionSnapshot:
        """Execute the full compilation pipeline and return an immutable RuntimeContributionSnapshot."""
        # Installed package trees are immutable integrity roots.  Keep Python from
        # materializing __pycache__ beside verified DLC sources, including for lazy
        # imports that occur after registration.
        sys.dont_write_bytecode = True
        activation_failures: list[DlcActivationFailure] = []

        # 1. Load registry records
        try:
            self.registry.load()
            records = self.registry.list_installed_dlcs()
        except Exception as exc:
            logger.warning(f"Failed to load InstalledDlcRegistry: {exc}; proceeding with built-ins only.")
            activation_failures.append(
                DlcActivationFailure(
                    dlc_id="__registry__",
                    error_code=DlcErrorCode.REGISTRY_CORRUPT.value,
                    message=str(exc),
                )
            )
            records = []

        # 2. Filter enabled DLCs and sort canonically by dlc_id
        enabled_records: list[InstalledDlcRecord] = [
            r for r in records if r.desired_enabled and r.selected_digest
        ]
        enabled_records.sort(key=lambda r: r.dlc_id)

        # 3. Resolve the immutable, owner-bound platform seed.
        seed = built_ins or platform_builtin_contributions()

        # 4. Accepted global state initialized with built-in contributions
        accepted_tool_registry = ToolRegistry(available_backends=frozenset({"in_process", "isolated_process"}))
        for tc in seed.tools:
            accepted_tool_registry.register(
                tc.tool,
                owner=tc.owner_id,
                package_digest=tc.package_digest,
                provider_name=tc.provider_name,
            )

        known_resolver_kinds: set[str] = {rc.kind for rc in seed.resource_resolvers}
        known_artifact_contract_keys = set(artifact_payload_contracts.snapshot())
        known_artifact_types: set[str] = set(_KNOWN_ARTIFACT_TYPES) | {
            artifact_type for artifact_type, _schema_version in known_artifact_contract_keys
        }
        known_artifact_type_owners = {
            artifact_type: "dbfox.core" for artifact_type in known_artifact_types
        }
        known_operations: set[tuple[str, str]] = set()
        known_completion_constraint_ids = {
            item.constraint.id for item in seed.completion_constraints
        }
        known_completion_support_ids = {
            item.support.id for item in seed.completion_supports
        }
        active_dlcs: list[ActivatedDlcIdentity] = []
        all_tools: list[ToolContribution] = list(seed.tools)
        all_resource_providers: list[ProjectResourceProvider] = list(seed.resource_providers)
        all_resource_resolvers: list[ResourceResolverContribution] = list(seed.resource_resolvers)
        all_context_contributors: list[Callable[[Session], ContextContributor]] = list(seed.context_contributors)
        all_completion_constraints = list(seed.completion_constraints)
        all_completion_supports = list(seed.completion_supports)
        all_capability_guidance = list(seed.capability_guidance)
        known_guidance_keys = {
            (item.owner_id, item.spec.id) for item in all_capability_guidance
        }
        all_credential_reference_probes = list(seed.credential_reference_probes)
        known_credential_probe_owner_ids = {
            item.owner_id for item in all_credential_reference_probes
        }
        all_artifact_contracts: list[ArtifactContractContribution] = []
        all_artifact_representations: list[ArtifactRepresentationContribution] = []
        known_artifact_representation_keys: set[tuple[str, str]] = set()
        all_operations: list[DlcOperationContribution] = []

        def _clone_tool_registry(base: ToolRegistry) -> ToolRegistry:
            cloned = ToolRegistry(available_backends=base._available_backends)
            for name in base.tool_names():
                cloned.register(
                    base.require(name),
                    owner=base.owner_of(name),
                    package_digest=base.package_digest_of(name),
                    provider_name=name,
                )
            return cloned

        # 5. Activate each enabled DLC in canonical order with strict transactional isolation
        for record in enabled_records:
            dlc_id = record.dlc_id
            selected_digest = record.selected_digest
            if not selected_digest:
                continue

            namespace = derive_dlc_namespace(dlc_id, selected_digest)
            try:
                # Pre-verification with strict identity binding
                manifest, package_root, trust_status, key_fingerprint = reverify_installed_package(
                    dlc_id,
                    selected_digest,
                    self.storage_root,
                    self.trust_store,
                    expected_version=record.package_version,
                    expected_publisher_key_id=record.publisher_key_id,
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
                            permissions=tuple(sorted(manifest.permissions)),
                        )
                    )
                    continue

                # Load trusted backend code in the Engine process.  Manifest
                # permissions constrain typed registrations; they are not an OS
                # sandbox.  R8A concluded NO-GO for untrusted activation.
                register_func = load_dlc_backend(package_root, manifest, selected_digest)

                # Prepare isolated data path for DLC
                data_path = self.storage_root / "data" / dlc_id
                data_path.mkdir(parents=True, exist_ok=True)
                runtime_info = DlcRuntimeInfo(
                    dlc_id=dlc_id,
                    package_version=manifest.version,
                    package_digest=selected_digest,
                    data_path=data_path,
                )

                # Staging execution
                staging = StagedDlcContributions(
                    dlc_id=dlc_id,
                    package_digest=selected_digest,
                    manifest=manifest,
                    runtime_info=runtime_info,
                )
                host = DefaultBackendExtensionHost(staging)
                register_func(host)

                # -----------------------------------------------------------------
                # Transactional Validation of ALL candidate contributions
                # -----------------------------------------------------------------

                # 1. Validate candidate tools against a clone of the accepted registry
                candidate_tool_registry = _clone_tool_registry(accepted_tool_registry)
                candidate_tools: list[ToolContribution] = []
                for tool in staging.tools:
                    # In R2 v1, installable DLC tools must use in_process execution backend
                    if tool.execution.backend != "in_process":
                        raise DlcError(
                            DlcErrorCode.PERMISSION_VIOLATION,
                            f"Tool '{tool.name}' from DLC '{dlc_id}' requested backend '{tool.execution.backend}'. "
                            "Dynamic DLC tools in v1 must use 'in_process' execution backend.",
                        )
                    _check_tool_permissions(manifest, tool)
                    _check_tool_resource_ownership(manifest, tool)
                    # Authoritative ToolRegistry validation on candidate clone
                    candidate_tool_registry.register(
                        tool,
                        owner=dlc_id,
                        package_digest=selected_digest,
                    )
                    candidate_tools.append(
                        ToolContribution(
                            tool=tool,
                            owner_id=dlc_id,
                            package_digest=selected_digest,
                            provider_name=candidate_tool_registry.provider_name_of(tool),
                        )
                    )

                # 2. Validate candidate resource resolvers
                candidate_resolvers: list[ResourceResolverContribution] = []
                candidate_resolver_kinds: set[str] = set()
                for kind, resolver in staging.resource_resolvers:
                    if not _owned_resource_kind(dlc_id, kind):
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Resource resolver kind '{kind}' must be namespaced under its owner '{dlc_id}.'.",
                        )
                    if kind in known_resolver_kinds or kind in candidate_resolver_kinds:
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Resource resolver kind '{kind}' from DLC '{dlc_id}' conflicts with an existing resolver",
                        )
                    candidate_resolver_kinds.add(kind)
                    candidate_resolvers.append(
                        ResourceResolverContribution(kind=kind, resolver=resolver, owner_id=dlc_id, binding="scope_only")
                    )

                # 3. Validate candidate resource providers
                candidate_providers: list[ProjectResourceProvider] = []
                for provider in staging.resource_providers:
                    def _make_adapted_provider(
                        p: ExtensionProjectResourceProvider,
                        owner_id: str = dlc_id,
                    ) -> ProjectResourceProvider:
                        def _adapted(
                            db: Session,
                            project_id: str,
                        ) -> tuple[ProjectResourceDescriptor, ...]:
                            del db
                            descriptors = tuple(p(project_id))
                            foreign = tuple(
                                descriptor.kind
                                for descriptor in descriptors
                                if not _owned_resource_kind(owner_id, descriptor.kind)
                            )
                            if foreign:
                                raise ValueError(
                                    f"DLC '{owner_id}' discovered foreign Resource kinds {foreign!r}"
                                )
                            return descriptors
                        return _adapted
                    candidate_providers.append(_make_adapted_provider(provider))

                # 4. Validate candidate context contributors
                candidate_context: list[Callable[[Session], ContextContributor]] = []
                for contributor in staging.context_contributors:
                    def _make_adapted_context(c: Any) -> Callable[[Session], ContextContributor]:
                        if isinstance(c, type):
                            return lambda _session: c()
                        if callable(c) and not hasattr(c, "build"):
                            return lambda _session: c()
                        return lambda _session: c
                    candidate_context.append(_make_adapted_context(contributor))

                candidate_guidance: list[CapabilityGuidanceContribution] = []
                candidate_guidance_keys: set[tuple[str, str]] = set()
                for guidance in staging.agent_guidance:
                    guidance_key = (dlc_id, guidance.id)
                    if guidance_key in known_guidance_keys or guidance_key in candidate_guidance_keys:
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Capability guidance '{guidance.id}' from DLC '{dlc_id}' conflicts with an existing contribution",
                        )
                    foreign_resources = tuple(
                        kind
                        for kind in guidance.applies_to_resource_kinds
                        if not _owned_resource_kind(dlc_id, kind)
                    )
                    foreign_artifacts = tuple(
                        artifact_type
                        for artifact_type in guidance.applies_to_artifact_types
                        if not _owned_resource_kind(dlc_id, artifact_type)
                    )
                    foreign_tools = tuple(
                        ref
                        for ref in guidance.tool_refs
                        if ref.owner_id != dlc_id
                    )
                    missing_tools = tuple(
                        ref
                        for ref in guidance.tool_refs
                        if candidate_tool_registry.get_by_key(ref) is None
                    )
                    if foreign_resources or foreign_artifacts or foreign_tools or missing_tools:
                        raise DlcError(
                            DlcErrorCode.PERMISSION_VIOLATION,
                            f"Capability guidance '{guidance.id}' from DLC '{dlc_id}' references foreign or unavailable capability contracts",
                        )
                    candidate_guidance_keys.add(guidance_key)
                    candidate_guidance.append(CapabilityGuidanceContribution(
                        spec=guidance,
                        owner_id=dlc_id,
                        package_digest=selected_digest,
                    ))

                # 5. Validate candidate artifact contracts
                candidate_artifacts: list[ArtifactContractContribution] = []
                candidate_artifact_types: set[str] = set()
                candidate_artifact_contract_keys: set[tuple[str, int]] = set()
                for art_type, schema_ver, validator in staging.artifact_contracts:
                    artifact_contract_key = (art_type, schema_ver)
                    existing_owner = known_artifact_type_owners.get(art_type)
                    if (
                        artifact_contract_key in known_artifact_contract_keys
                        or artifact_contract_key in candidate_artifact_contract_keys
                        or (existing_owner is not None and existing_owner != dlc_id)
                    ):
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Artifact contract '{art_type}' v{schema_ver} from DLC '{dlc_id}' conflicts with an existing contract",
                        )
                    candidate_artifact_types.add(art_type)
                    candidate_artifact_contract_keys.add(artifact_contract_key)
                    candidate_artifacts.append(
                        ArtifactContractContribution(
                            artifact_type=art_type,
                            schema_version=schema_ver,
                            validator=validator,
                            owner_id=dlc_id,
                        )
                    )

                candidate_artifact_representations: list[
                    ArtifactRepresentationContribution
                ] = []
                candidate_artifact_representation_keys: set[tuple[str, str]] = set()
                for (
                    art_type,
                    representation_type,
                    representation_provider,
                ) in staging.artifact_representations:
                    if art_type not in candidate_artifact_types:
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Artifact representation '{representation_type}' for '{art_type}' "
                            f"from DLC '{dlc_id}' must target an Artifact contract registered by the same DLC",
                        )
                    representation_key = (art_type, representation_type)
                    if (
                        representation_key in known_artifact_representation_keys
                        or representation_key in candidate_artifact_representation_keys
                    ):
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Artifact representation '{representation_type}' for '{art_type}' "
                            f"from DLC '{dlc_id}' conflicts with an existing provider",
                        )
                    candidate_artifact_representation_keys.add(representation_key)
                    candidate_artifact_representations.append(
                        ArtifactRepresentationContribution(
                            artifact_type=art_type,
                            representation_type=representation_type,
                            provider=representation_provider,
                            owner_id=dlc_id,
                        )
                    )

                candidate_completion_constraints: list[CompletionConstraintContribution] = []
                candidate_constraint_ids: set[str] = set()
                for constraint in staging.completion_constraints:
                    if (
                        constraint.id in known_completion_constraint_ids
                        or constraint.id in candidate_constraint_ids
                    ):
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Completion constraint '{constraint.id}' from DLC '{dlc_id}' conflicts with an existing contribution",
                        )
                    candidate_constraint_ids.add(constraint.id)
                    candidate_completion_constraints.append(
                        CompletionConstraintContribution(
                            constraint=constraint,
                            owner_id=dlc_id,
                        )
                    )

                candidate_completion_supports: list[CompletionSupportContribution] = []
                candidate_support_ids: set[str] = set()
                for support in staging.completion_supports:
                    if (
                        support.id in known_completion_support_ids
                        or support.id in candidate_support_ids
                    ):
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Completion support '{support.id}' from DLC '{dlc_id}' conflicts with an existing contribution",
                        )
                    candidate_support_ids.add(support.id)
                    candidate_completion_supports.append(
                        CompletionSupportContribution(
                            support=support,
                            owner_id=dlc_id,
                        )
                    )

                candidate_credential_reference_probes: list[
                    CredentialReferenceProbeContribution
                ] = []
                if (
                    staging.credential_reference_probes
                    and dlc_id in known_credential_probe_owner_ids
                ):
                    raise DlcError(
                        DlcErrorCode.REGISTRATION_CONFLICT,
                        f"Credential ownership probe for '{dlc_id}' is already registered",
                    )
                for probe in staging.credential_reference_probes:
                    def _make_credential_probe(
                        package_probe: Callable[[frozenset[str]], bool],
                    ) -> Callable[[Session, frozenset[str]], bool]:
                        return lambda _session, refs: bool(package_probe(refs))

                    candidate_credential_reference_probes.append(
                        CredentialReferenceProbeContribution(
                            probe=_make_credential_probe(probe),
                            owner_id=dlc_id,
                        )
                    )

                # 6. Validate candidate operations
                candidate_operations: list[DlcOperationContribution] = []
                candidate_op_keys: set[tuple[str, str]] = set()
                if any(
                    op_spec.credential_references is not None
                    for op_spec in staging.operations
                ) and not staging.credential_reference_probes:
                    raise DlcError(
                        DlcErrorCode.REGISTRATION_CONFLICT,
                        f"DLC '{dlc_id}' declares credential-adopting operations without an ownership probe",
                    )
                for op_spec in staging.operations:
                    _check_operation_permissions(manifest, op_spec)
                    op_key = (dlc_id, op_spec.name)
                    if op_key in known_operations or op_key in candidate_op_keys:
                        raise DlcError(
                            DlcErrorCode.REGISTRATION_CONFLICT,
                            f"Operation '{op_spec.name}' from DLC '{dlc_id}' is already registered",
                        )
                    candidate_op_keys.add(op_key)
                    candidate_operations.append(
                        DlcOperationContribution(dlc_id=dlc_id, spec=op_spec)
                    )

                # -----------------------------------------------------------------
                # PROMOTE: All validations passed, commit candidate contributions
                # -----------------------------------------------------------------

                # Promote tools & registry
                accepted_tool_registry = candidate_tool_registry
                all_tools.extend(candidate_tools)

                # Promote resolvers & providers
                known_resolver_kinds.update(candidate_resolver_kinds)
                all_resource_resolvers.extend(candidate_resolvers)
                all_resource_providers.extend(candidate_providers)

                # Promote context
                all_context_contributors.extend(candidate_context)
                known_guidance_keys.update(candidate_guidance_keys)
                all_capability_guidance.extend(candidate_guidance)

                known_completion_constraint_ids.update(candidate_constraint_ids)
                known_completion_support_ids.update(candidate_support_ids)
                all_completion_constraints.extend(candidate_completion_constraints)
                all_completion_supports.extend(candidate_completion_supports)
                all_credential_reference_probes.extend(
                    candidate_credential_reference_probes
                )
                known_credential_probe_owner_ids.update(
                    item.owner_id
                    for item in candidate_credential_reference_probes
                )

                # Promote artifacts
                known_artifact_types.update(candidate_artifact_types)
                known_artifact_contract_keys.update(candidate_artifact_contract_keys)
                known_artifact_type_owners.update(
                    {artifact_type: dlc_id for artifact_type in candidate_artifact_types}
                )
                all_artifact_contracts.extend(candidate_artifacts)
                known_artifact_representation_keys.update(
                    candidate_artifact_representation_keys
                )
                all_artifact_representations.extend(candidate_artifact_representations)

                # Promote operations
                known_operations.update(candidate_op_keys)
                all_operations.extend(candidate_operations)

                # Promote active DLC identity
                active_dlcs.append(
                    ActivatedDlcIdentity(
                        dlc_id=dlc_id,
                        package_version=manifest.version,
                        package_digest=selected_digest,
                        publisher_key_id=key_fingerprint,
                        trust_status=trust_status,
                        frontend_entrypoint=manifest.entrypoints.frontend,
                        permissions=tuple(sorted(manifest.permissions)),
                    )
                )

            except Exception as exc:
                exc_code = getattr(exc, "code", None)
                if isinstance(exc_code, DlcErrorCode):
                    err_code = exc_code.value
                elif exc_code is not None:
                    err_code = str(exc_code)
                else:
                    err_code = type(exc).__name__
                logger.error(f"Failed to activate DLC '{dlc_id}': {exc}", exc_info=True)
                activation_failures.append(
                    DlcActivationFailure(
                        dlc_id=dlc_id,
                        error_code=err_code,
                        message=str(exc),
                    )
                )
                purge_dlc_namespace(namespace)
                # Broken DLC isolation: candidate state discarded, accepted state untouched

        # 6. Compute deterministic snapshot ID
        active_dlc_tuple = tuple(active_dlcs)
        snapshot_id = compute_snapshot_id(
            active_dlc_tuple,
            built_in_identifiers=seed.identifiers,
        )

        return RuntimeContributionSnapshot(
            snapshot_id=snapshot_id,
            active_dlcs=active_dlc_tuple,
            tools=tuple(all_tools),
            resource_providers=tuple(all_resource_providers),
            resource_resolvers=tuple(all_resource_resolvers),
            context_contributors=tuple(all_context_contributors),
            completion_constraints=tuple(all_completion_constraints),
            completion_supports=tuple(all_completion_supports),
            capability_guidance=tuple(all_capability_guidance),
            artifact_contracts=tuple(all_artifact_contracts),
            artifact_representations=tuple(all_artifact_representations),
            operations=tuple(all_operations),
            credential_reference_probes=tuple(all_credential_reference_probes),
            activation_failures=tuple(activation_failures),
        )
