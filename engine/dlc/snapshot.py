"""Immutable Runtime Contribution Snapshot and composition identity."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.agent.context_fragment import ContextContributor
from engine.agent.resource_refs import ProjectResourceProvider
from engine.dlc.api import DlcOperationSpec
from engine.dlc.compat import CURRENT_DBFOX_VERSION
from engine.dlc.integrity import canonical_json_bytes
from engine.dlc.trust import DlcTrustStatus
from engine.tools.runtime.base import BaseTool


@dataclass(frozen=True)
class ActivatedDlcIdentity:
    """Minimal immutable identity of an active DLC participating in the runtime."""

    dlc_id: str
    package_version: str
    package_digest: str
    publisher_key_id: str | None = None
    trust_status: DlcTrustStatus = DlcTrustStatus.TRUSTED_SIGNED
    frontend_entrypoint: str | None = None


@dataclass(frozen=True)
class ToolContribution:
    """A tool contribution bound to its capability owner and implementation digest."""

    tool: BaseTool[Any, Any]
    owner_id: str
    package_digest: str | None = None


@dataclass(frozen=True)
class ResourceResolverContribution:
    """A resource resolver contribution bound to its capability owner and platform binding."""

    kind: str
    resolver: Any
    owner_id: str
    binding: Literal["scope_only", "metadata_session"] = "scope_only"


@dataclass(frozen=True)
class ArtifactContractContribution:
    """An Artifact payload contract contribution bound to its capability owner."""

    artifact_type: str
    schema_version: int
    validator: type[BaseModel]
    owner_id: str


@dataclass(frozen=True)
class DlcOperationContribution:
    """A registered typed operation bound to a DLC."""

    dlc_id: str
    spec: DlcOperationSpec


@dataclass(frozen=True)
class DlcActivationFailure:
    """Bounded diagnostic for a DLC that failed pre-verification or activation."""

    dlc_id: str
    error_code: str
    message: str = ""


@dataclass(frozen=True)
class RuntimeDlcActivationProjection:
    """Wire-safe projection of active DLCs for future R3 Rust asset serving."""

    snapshot_id: str
    active_dlcs: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class RuntimeContributionSnapshot:
    """The central immutable composition result of all active built-in and DLC contributions.

    This snapshot represents the process-level runtime composition truth for the current
    engine process. It is NOT a database table or persistent domain model.
    """

    snapshot_id: str
    active_dlcs: tuple[ActivatedDlcIdentity, ...]
    tools: tuple[ToolContribution, ...]
    resource_providers: tuple[ProjectResourceProvider, ...]
    resource_resolvers: tuple[ResourceResolverContribution, ...]
    context_contributors: tuple[Callable[[Session], ContextContributor], ...]
    artifact_contracts: tuple[ArtifactContractContribution, ...]
    operations: tuple[DlcOperationContribution, ...]
    activation_failures: tuple[DlcActivationFailure, ...] = ()


    def derive_r3_projection(self) -> RuntimeDlcActivationProjection:
        """Derive the wire-safe projection for future R3 Rust asset protocol handoff."""
        return RuntimeDlcActivationProjection(
            snapshot_id=self.snapshot_id,
            active_dlcs=tuple(
                {
                    "dlc_id": d.dlc_id,
                    "package_version": d.package_version,
                    "package_digest": d.package_digest,
                    "frontend_entrypoint": d.frontend_entrypoint,
                }
                for d in self.active_dlcs
            ),
        )

    def get_operation(self, dlc_id: str, operation_name: str) -> DlcOperationContribution | None:
        """Look up a registered operation by DLC id and operation name."""
        for op in self.operations:
            if op.dlc_id == dlc_id and op.spec.name == operation_name:
                return op
        return None


def compute_snapshot_id(
    active_dlcs: tuple[ActivatedDlcIdentity, ...],
    built_in_identifiers: tuple[str, ...] = ("builtin.data", "builtin.workspace", "builtin.github"),
) -> str:
    """Deterministically compute the runtime snapshot ID from composition identity."""
    sorted_dlc_payload = [
        {
            "dlc_id": d.dlc_id,
            "package_digest": d.package_digest,
            "package_version": d.package_version,
        }
        for d in sorted(active_dlcs, key=lambda x: x.dlc_id)
    ]
    identity_payload = {
        "dbfox_version": CURRENT_DBFOX_VERSION,
        "built_ins": list(built_in_identifiers),
        "active_dlcs": sorted_dlc_payload,
    }
    canonical_bytes = canonical_json_bytes(identity_payload)
    return f"snap_{hashlib.sha256(canonical_bytes).hexdigest()}"
