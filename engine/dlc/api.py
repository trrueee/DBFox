"""Public Extension API v2 for DBFox Runtime DLCs.

This module is the stable, narrow public interface exposed to Runtime DLCs.
DLC implementations MUST import extension contracts from this module (or
``dbfox_dlc_api``), and private imports from DBFox internals are unsupported
and outside Extension API compatibility.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Literal, Protocol, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.context_fragment import (
    ContextArtifactObservation,
    ContextContributionInput,
    ContextContributor,
    ContextFragment,
    ContextLane,
    MAX_CONTEXT_FRAGMENT_CHARS,
    MAX_CONTEXT_FRAGMENTS_PER_CONTRIBUTOR,
    MAX_CONTEXT_ARTIFACT_OBSERVATIONS,
    MAX_CONTEXT_ARTIFACT_PAYLOAD_BYTES,
)
from engine.agent.artifact import (
    Artifact,
    ArtifactDraft,
    ArtifactRelationDraft,
    ArtifactRelationType,
    ArtifactVisibility,
)
from engine.agent.artifact_view import (
    ArtifactChartData,
    ArtifactChartViewProvider,
    ArtifactCsvStream,
    ArtifactTableExportRequest,
    ArtifactTablePage,
    ArtifactTablePageRequest,
    ArtifactTableViewProvider,
    ArtifactViewError,
    ArtifactViewFilter,
    ArtifactViewSort,
)
from engine.agent.completion import (
    CompletionConstraint,
    CompletionSupport,
    SemanticArtifactCompletionSupport,
    SemanticCitationConstraint,
)
from engine.agent.guidance import CapabilityGuidanceSpec
from engine.errors import ToolInputError
from engine.app.safe_errors import log_extension_diagnostic, log_extension_exception
from engine.json_codec import dumps as json_dumps
from engine.agent.resource_refs import (
    ProjectResourceDescriptor,
    RequestedResourceRef,
)
from engine.tools.runtime.attempt import ResourceKey, ResourceScopeRef, ScopedResourceResolver
from engine.tools.runtime.registry import ToolKey
from engine.tools.runtime.base import (
    BaseTool,
    ToolCapability,
    ToolExecutionSpec,
    ToolResourceRequirement,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
    ToolRecoveryPolicy,
)
from engine.tools.runtime.result import ToolOutcome, ToolReconciliation
from engine.tools.runtime.admission import ToolAdmissionContext, ToolAdmissionDecision
from engine.tools.runtime.observation import ToolObservationProjection
from engine.tools.runtime.semantics import ToolSemanticSpec

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)

# Neutral project resource provider contract: DLC receives only project_id (no Session)
ExtensionProjectResourceProvider: TypeAlias = Callable[[str], Sequence[ProjectResourceDescriptor]]

# Neutral context contributor contract: DLC receives only ContextContributionInput (no Session)
ExtensionContextContributor: TypeAlias = ContextContributor
ExtensionContextContributorFactory: TypeAlias = Callable[[], ContextContributor]


class ExtensionToolRunContext(Protocol):
    """Narrow execution context exposed to installable DLC tools."""

    invocation_id: str

    @property
    def execution_mode(self) -> str:
        """Return the Host-owned execution mode for this invocation."""
        ...

    def is_cancelled(self) -> bool:
        """Return whether the Host cancelled or timed out this invocation."""
        ...

    def resource(self, ref: ResourceScopeRef | ResourceKey) -> Any:
        """Return one authorized resource selected by its full identity."""
        ...

    def resources(self, kind: str) -> tuple[Any, ...]:
        """Return every authorized resource of ``kind`` in frozen scope order."""
        ...

    def scopes(self, kind: str) -> tuple[ResourceScopeRef, ...]:
        """Return the frozen scope refs for every authorized resource of ``kind``."""
        ...

    def require_one(self, kind: str) -> Any:
        """Return the sole resource of ``kind`` or reject missing/ambiguous scope."""
        ...

    def artifact(self, artifact_id: str) -> Artifact:
        """Return one immutable Artifact only when it belongs to the invoking Run."""
        ...

    def artifacts_relating_to(
        self,
        artifact_id: str,
        relation: ArtifactRelationType,
    ) -> tuple[Artifact, ...]:
        """Return current-Run Artifacts relating to one immutable source."""
        ...

    def approval_authorizes(
        self,
        approval_subject: dict[str, Any],
        resource_ref: ResourceScopeRef | None,
    ) -> bool:
        """Verify the current invocation's exact durable approval contract."""
        ...


class DlcOperationError(Exception):
    """Bounded, client-safe failure raised by a typed DLC operation."""

    _ALLOWED_STATUS_CODES = frozenset({400, 404, 409, 429, 502, 503})

    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        normalized_code = str(code).strip()
        normalized_message = str(message).strip()
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", normalized_code) is None:
            raise ValueError("DLC operation error code must be uppercase snake case")
        if not 1 <= len(normalized_message) <= 512:
            raise ValueError("DLC operation error message must contain 1 to 512 characters")
        if status_code not in self._ALLOWED_STATUS_CODES:
            raise ValueError("DLC operation error status_code is not client-safe")
        super().__init__(normalized_message)
        self.code = normalized_code
        self.message = normalized_message
        self.status_code = status_code


@dataclass(frozen=True)
class DlcActionToolResult:
    """Structured outcome returned after one durably settled action Tool call."""

    status: Literal["success", "failed"]
    output: dict[str, Any]
    artifacts: tuple[Artifact, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True)
class DlcActionRunResult:
    """Durable identifiers and Artifacts produced by a completed action Run."""

    run_id: str
    session_id: str
    artifacts: tuple[Artifact, ...]


class DlcActionRun(Protocol):
    """One Host-owned durable Run driven by an explicit DLC Workbench action."""

    @property
    def run_id(self) -> str: ...

    @property
    def session_id(self) -> str: ...

    def invoke(self, tool_name: str, raw_input: dict[str, Any]) -> DlcActionToolResult:
        """Invoke and durably settle one Tool owned by the calling DLC."""
        ...

    def complete(
        self,
        *,
        summary: str,
        selected_artifact_id: str | None = None,
    ) -> DlcActionRunResult:
        """Atomically terminalize this action Run."""
        ...

    def __enter__(self) -> "DlcActionRun": ...

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> Literal[False]: ...


class DlcActionRunsHost(Protocol):
    """Kernel lifecycle service exposed to project-scoped DLC operations."""

    def start(
        self,
        *,
        title: str,
        question: str,
        requested_resources: tuple[RequestedResourceRef, ...],
        session_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> DlcActionRun:
        """Create one frozen-authority action Run for the calling DLC."""
        ...


@dataclass(frozen=True)
class DlcRuntimeInfo:
    """Minimal immutable host-owned runtime identity for the DLC."""

    dlc_id: str
    package_version: str
    package_digest: str
    data_path: Path


@dataclass(frozen=True)
class DlcOperationContext:
    """Invocation context passed to a DLC operation handler."""

    dlc_id: str
    operation_name: str
    project_id: str | None = None
    action_runs: DlcActionRunsHost | None = None

    def require_action_runs(self) -> DlcActionRunsHost:
        if self.action_runs is None:
            raise RuntimeError("This operation has no project action Run host")
        return self.action_runs


@dataclass(frozen=True)
class DlcOperationSpec:
    """Typed specification for a domain management operation / RPC."""

    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[Any, DlcOperationContext], Any]
    scope: Literal["machine", "project"] = "machine"
    capabilities: tuple[str, ...] = ()
    description: str = ""
    max_output_bytes: int = 1_048_576  # 1 MiB
    credential_references: Callable[[Any], frozenset[str]] | None = None
    credential_lease_required: bool = False


class ExtensionToolsHost(Protocol):
    """Registration surface for DLC Tools."""

    def register(self, tool: BaseTool[Any, Any]) -> None:
        """Register an executable tool into the DLC's staged contribution set."""
        ...


class ExtensionResourcesHost(Protocol):
    """Registration surface for DLC Resource discovery and resolution."""

    def register_provider(self, provider: ExtensionProjectResourceProvider) -> None:
        """Register a neutral project resource discovery function."""
        ...

    def register_resolver(self, kind: str, resolver: ScopedResourceResolver) -> None:
        """Register a scoped resource resolver for a specific resource kind."""
        ...


class ExtensionContextHost(Protocol):
    """Registration surface for DLC Context contributors."""

    def register(
        self,
        contributor: (
            ExtensionContextContributor
            | ExtensionContextContributorFactory
            | type[ExtensionContextContributor]
        ),
    ) -> None:
        """Register a neutral ContextContributor or zero-arg factory."""
        ...


class ExtensionAgentGuidanceHost(Protocol):
    """Registration surface for static trusted capability instructions."""

    def register(self, guidance: CapabilityGuidanceSpec) -> None:
        ...


class ExtensionArtifactsHost(Protocol):
    """Registration surface for DLC Artifact payload contracts."""

    def register(
        self,
        artifact_type: str,
        schema_version: int,
        validator: type[BaseModel],
    ) -> None:
        """Register a concrete Artifact payload write validation schema."""
        ...

    def register_table_view(
        self,
        artifact_type: str,
        provider: ArtifactTableViewProvider,
    ) -> None:
        """Register the durable table reader for one owned Artifact type."""
        ...

    def register_chart_view(
        self,
        artifact_type: str,
        provider: ArtifactChartViewProvider,
    ) -> None:
        """Register the durable chart reader for one owned Artifact type."""
        ...


class ExtensionOperationsHost(Protocol):
    """Registration surface for DLC typed operations / management RPCs."""

    def register(self, spec: DlcOperationSpec) -> None:
        """Register a typed operation specification."""
        ...


class ExtensionCompletionHost(Protocol):
    """Registration surface for terminal completion semantics."""

    def register_constraint(self, constraint: CompletionConstraint) -> None:
        """Register one monotonic terminal constraint."""
        ...

    def register_support(self, support: CompletionSupport) -> None:
        """Register one durable evidence family used by terminalization."""
        ...


class ExtensionCredentialsHost(Protocol):
    """Permission-scoped access to opaque OS credential references.

    The host deliberately exposes no enumeration and no global vault object.
    Installable DLCs can resolve only the exact credential kinds declared in
    their signed manifest.
    """

    def get(self, credential_ref: str, *, kind: str) -> str | None:
        """Resolve one opaque reference after exact kind/permission checks."""
        ...

    def register_reference_probe(
        self,
        probe: Callable[[frozenset[str]], bool],
    ) -> None:
        """Register a read-only ownership probe used by credential recovery."""
        ...


class BackendExtensionHost(Protocol):
    """Imperative typed host object passed to ``register(host)`` in backend/entry.py."""

    @property
    def runtime_info(self) -> DlcRuntimeInfo: ...

    @property
    def tools(self) -> ExtensionToolsHost: ...

    @property
    def resources(self) -> ExtensionResourcesHost: ...

    @property
    def context(self) -> ExtensionContextHost: ...

    @property
    def agent_guidance(self) -> ExtensionAgentGuidanceHost: ...

    @property
    def artifacts(self) -> ExtensionArtifactsHost: ...

    @property
    def completion(self) -> ExtensionCompletionHost: ...

    @property
    def operations(self) -> ExtensionOperationsHost: ...

    @property
    def credentials(self) -> ExtensionCredentialsHost: ...


__all__ = [
    "Artifact",
    # Host & Registration interfaces
    "BackendExtensionHost",
    "ExtensionToolsHost",
    "ExtensionResourcesHost",
    "ExtensionContextHost",
    "ExtensionAgentGuidanceHost",
    "CapabilityGuidanceSpec",
    "ExtensionArtifactsHost",
    "ExtensionCompletionHost",
    "ExtensionOperationsHost",
    "ExtensionCredentialsHost",
    "DlcRuntimeInfo",
    "DlcOperationError",
    # Tool contracts
    "BaseTool",
    "ToolInputModel",
    "ToolOutputModel",
    "ToolPolicy",
    "ToolExecutionSpec",
    "ToolResourceRequirement",
    "ToolPresentation",
    "ToolRecoveryPolicy",
    "ToolCapability",
    "ToolSemanticSpec",
    "ToolOutcome",
    "ToolReconciliation",
    "ToolAdmissionContext",
    "ToolAdmissionDecision",
    "ToolObservationProjection",
    "ToolInputError",
    "ToolKey",
    "log_extension_diagnostic",
    "log_extension_exception",
    "json_dumps",
    "ExtensionToolRunContext",
    "ArtifactDraft",
    "ArtifactRelationDraft",
    "ArtifactRelationType",
    "ArtifactVisibility",
    "ArtifactCsvStream",
    "ArtifactChartData",
    "ArtifactChartViewProvider",
    "ArtifactTableExportRequest",
    "ArtifactTablePage",
    "ArtifactTablePageRequest",
    "ArtifactTableViewProvider",
    "ArtifactViewError",
    "ArtifactViewFilter",
    "ArtifactViewSort",
    "CompletionConstraint",
    "CompletionSupport",
    "SemanticArtifactCompletionSupport",
    "SemanticCitationConstraint",
    # Resource contracts
    "ProjectResourceDescriptor",
    "ExtensionProjectResourceProvider",
    "RequestedResourceRef",
    "ResourceKey",
    "ResourceScopeRef",
    "ScopedResourceResolver",
    # Context contracts
    "ContextContributor",
    "ContextArtifactObservation",
    "ExtensionContextContributor",
    "ExtensionContextContributorFactory",
    "ContextContributionInput",
    "ContextFragment",
    "ContextLane",
    "MAX_CONTEXT_FRAGMENT_CHARS",
    "MAX_CONTEXT_FRAGMENTS_PER_CONTRIBUTOR",
    "MAX_CONTEXT_ARTIFACT_OBSERVATIONS",
    "MAX_CONTEXT_ARTIFACT_PAYLOAD_BYTES",
    # Operation contracts
    "DlcOperationSpec",
    "DlcOperationContext",
    "DlcActionRun",
    "DlcActionRunResult",
    "DlcActionRunsHost",
    "DlcActionToolResult",
    # Pydantic primitives
    "BaseModel",
    "Field",
    "ConfigDict",
]
