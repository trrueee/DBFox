"""Public Extension API v1 for DBFox Runtime DLCs.

This module is the stable, narrow public interface exposed to Runtime DLCs.
DLC implementations MUST import extension contracts from this module (or
``dbfox_dlc_api``), and MUST NOT import private DBFox internals (such as
``engine.models``, ``engine.agent.*``, or ``engine.runtime_composition``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.context_fragment import (
    ContextContributionInput,
    ContextContributor,
    ContextFragment,
    ContextLane,
)
from engine.agent.resource_refs import (
    ProjectResourceDescriptor,
    ProjectResourceProvider,
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


@dataclass(frozen=True)
class DlcOperationContext:
    """Invocation context passed to a DLC operation handler."""

    dlc_id: str
    operation_name: str
    caller_info: dict[str, Any] | None = None


@dataclass(frozen=True)
class DlcOperationSpec:
    """Typed specification for a domain management operation / RPC."""

    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[Any, DlcOperationContext], Any] | Callable[[Any], Any]
    description: str = ""
    max_output_bytes: int = 1_048_576  # 1 MiB


class ExtensionToolsHost(Protocol):
    """Registration surface for DLC Tools."""

    def register(self, tool: BaseTool[Any, Any]) -> None:
        """Register an executable tool into the DLC's staged contribution set."""
        ...


class ExtensionResourcesHost(Protocol):
    """Registration surface for DLC Resource discovery and resolution."""

    def register_provider(self, provider: ProjectResourceProvider) -> None:
        """Register a project resource discovery function."""
        ...

    def register_resolver(self, kind: str, resolver: ScopedResourceResolver) -> None:
        """Register a scoped resource resolver for a specific resource kind."""
        ...


class ExtensionContextHost(Protocol):
    """Registration surface for DLC Context contributors."""

    def register(self, contributor_factory: Callable[[Any], ContextContributor]) -> None:
        """Register a ContextContributor factory (accepting a Session)."""
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
    "ProjectResourceProvider",
    "RequestedResourceRef",
    "ResourceScopeRef",
    "ScopedResourceResolver",
    # Context contracts
    "ContextContributor",
    "ContextContributionInput",
    "ContextFragment",
    "ContextLane",
    # Operation contracts
    "DlcOperationSpec",
    "DlcOperationContext",
    # Pydantic primitives
    "BaseModel",
    "Field",
    "ConfigDict",
]
