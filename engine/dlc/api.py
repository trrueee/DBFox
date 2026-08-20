"""Public Extension API v1 for DBFox Runtime DLCs.

This module is the stable, narrow public interface exposed to Runtime DLCs.
DLC implementations MUST import extension contracts from this module (or
``dbfox_dlc_api``), and private imports from DBFox internals are unsupported
and outside Extension API compatibility.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.context_fragment import (
    ContextContributionInput,
    ContextContributor,
    ContextFragment,
    ContextLane,
    MAX_CONTEXT_FRAGMENT_CHARS,
    MAX_CONTEXT_FRAGMENTS_PER_CONTRIBUTOR,
)
from engine.agent.resource_refs import (
    ProjectResourceDescriptor,
    RequestedResourceRef,
)
from engine.tools.runtime.attempt import ResourceScopeRef, ScopedResourceResolver
from engine.tools.runtime.base import (
    BaseTool,
    ToolCapability,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
    ToolRecoveryPolicy,
)

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)

# Neutral project resource provider contract: DLC receives only project_id (no Session)
ExtensionProjectResourceProvider: TypeAlias = Callable[[str], Sequence[ProjectResourceDescriptor]]

# Neutral context contributor contract: DLC receives only ContextContributionInput (no Session)
ExtensionContextContributor: TypeAlias = ContextContributor
ExtensionContextContributorFactory: TypeAlias = Callable[[], ContextContributor]


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


class ExtensionOperationsHost(Protocol):
    """Registration surface for DLC typed operations / management RPCs."""

    def register(self, spec: DlcOperationSpec) -> None:
        """Register a typed operation specification."""
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
    def artifacts(self) -> ExtensionArtifactsHost: ...

    @property
    def operations(self) -> ExtensionOperationsHost: ...


__all__ = [
    # Host & Registration interfaces
    "BackendExtensionHost",
    "ExtensionToolsHost",
    "ExtensionResourcesHost",
    "ExtensionContextHost",
    "ExtensionArtifactsHost",
    "ExtensionOperationsHost",
    "DlcRuntimeInfo",
    # Tool contracts
    "BaseTool",
    "ToolInputModel",
    "ToolOutputModel",
    "ToolPolicy",
    "ToolExecutionSpec",
    "ToolPresentation",
    "ToolRecoveryPolicy",
    "ToolCapability",
    # Resource contracts
    "ProjectResourceDescriptor",
    "ExtensionProjectResourceProvider",
    "RequestedResourceRef",
    "ResourceScopeRef",
    "ScopedResourceResolver",
    # Context contracts
    "ContextContributor",
    "ExtensionContextContributor",
    "ExtensionContextContributorFactory",
    "ContextContributionInput",
    "ContextFragment",
    "ContextLane",
    "MAX_CONTEXT_FRAGMENT_CHARS",
    "MAX_CONTEXT_FRAGMENTS_PER_CONTRIBUTOR",
    # Operation contracts
    "DlcOperationSpec",
    "DlcOperationContext",
    # Pydantic primitives
    "BaseModel",
    "Field",
    "ConfigDict",
]
