"""Transactional host implementation and staging builder for DLC registration."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.agent.context_fragment import ContextContributor
from engine.agent.resource_refs import ProjectResourceProvider
from engine.dlc.api import (
    BackendExtensionHost as IBackendExtensionHost,
    DlcOperationSpec,
    ExtensionArtifactsHost as IExtensionArtifactsHost,
    ExtensionContextHost as IExtensionContextHost,
    ExtensionOperationsHost as IExtensionOperationsHost,
    ExtensionResourcesHost as IExtensionResourcesHost,
    ExtensionToolsHost as IExtensionToolsHost,
)
from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.manifest import DlcManifest
from engine.tools.runtime.attempt import ScopedResourceResolver
from engine.tools.runtime.base import BaseTool

_OPERATION_NAME_PATTERN = re.compile(r"^[a-z0-9_.-]{1,64}$")
_ARTIFACT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*(?:[.:][a-z][a-z0-9_.-]*)+$")


@dataclass
class StagedDlcContributions:
    """Staging container collecting all contributions registered by one DLC during its activation."""

    dlc_id: str
    package_digest: str
    manifest: DlcManifest
    tools: list[BaseTool[Any, Any]] = field(default_factory=list)
    resource_providers: list[ProjectResourceProvider] = field(default_factory=list)
    resource_resolvers: list[tuple[str, ScopedResourceResolver]] = field(default_factory=list)
    context_contributors: list[Callable[[Session], ContextContributor]] = field(default_factory=list)
    artifact_contracts: list[tuple[str, int, type[BaseModel]]] = field(default_factory=list)
    operations: list[DlcOperationSpec] = field(default_factory=list)


class _StagedToolsHost:
    def __init__(self, staging: StagedDlcContributions) -> None:
        self._staging = staging

    def register(self, tool: BaseTool[Any, Any]) -> None:
        if not isinstance(tool, BaseTool):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' attempted to register a non-BaseTool object: {tool!r}",
            )
        # Check duplicate tool name within this DLC
        for existing in self._staging.tools:
            if existing.name == tool.name:
                raise DlcError(
                    DlcErrorCode.REGISTRATION_CONFLICT,
                    f"DLC '{self._staging.dlc_id}' registered duplicate tool name '{tool.name}'",
                )
        self._staging.tools.append(tool)


class _StagedResourcesHost:
    def __init__(self, staging: StagedDlcContributions) -> None:
        self._staging = staging

    def register_provider(self, provider: ProjectResourceProvider) -> None:
        if not callable(provider):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' registered a non-callable resource provider",
            )
        self._staging.resource_providers.append(provider)

    def register_resolver(self, kind: str, resolver: ScopedResourceResolver) -> None:
        if not isinstance(kind, str) or not kind.strip():
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' provided an invalid resource resolver kind: {kind!r}",
            )
        if not callable(resolver):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' registered a non-callable resource resolver for kind '{kind}'",
            )
        for existing_kind, _ in self._staging.resource_resolvers:
            if existing_kind == kind:
                raise DlcError(
                    DlcErrorCode.REGISTRATION_CONFLICT,
                    f"DLC '{self._staging.dlc_id}' registered duplicate resource resolver for kind '{kind}'",
                )
        self._staging.resource_resolvers.append((kind, resolver))


class _StagedContextHost:
    def __init__(self, staging: StagedDlcContributions) -> None:
        self._staging = staging

    def register(self, contributor_factory: Callable[[Any], ContextContributor]) -> None:
        if not callable(contributor_factory):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' registered a non-callable context contributor factory",
            )
        self._staging.context_contributors.append(contributor_factory)


class _StagedArtifactsHost:
    def __init__(self, staging: StagedDlcContributions) -> None:
        self._staging = staging

    def register(
        self,
        artifact_type: str,
        schema_version: int,
        validator: type[BaseModel],
    ) -> None:
        if not isinstance(artifact_type, str) or not _ARTIFACT_TYPE_PATTERN.fullmatch(artifact_type):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' registered an invalid namespaced artifact type '{artifact_type}'. "
                "Artifact types must be lowercase namespaced strings (e.g. 'acme.analysis').",
            )
        if not isinstance(schema_version, int) or schema_version < 1:
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' registered invalid artifact schema_version={schema_version}",
            )
        if not (isinstance(validator, type) and issubclass(validator, BaseModel)):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' artifact validator must be a Pydantic BaseModel subclass",
            )
        for existing_type, existing_ver, _ in self._staging.artifact_contracts:
            if existing_type == artifact_type and existing_ver == schema_version:
                raise DlcError(
                    DlcErrorCode.REGISTRATION_CONFLICT,
                    f"DLC '{self._staging.dlc_id}' registered duplicate artifact contract for '{artifact_type}' v{schema_version}",
                )
        self._staging.artifact_contracts.append((artifact_type, schema_version, validator))


class _StagedOperationsHost:
    def __init__(self, staging: StagedDlcContributions) -> None:
        self._staging = staging

    def register(self, spec: DlcOperationSpec) -> None:
        if not isinstance(spec, DlcOperationSpec):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' passed invalid DlcOperationSpec: {spec!r}",
            )
        if not _OPERATION_NAME_PATTERN.fullmatch(spec.name):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' operation name '{spec.name}' is invalid. "
                "Operation names must use lowercase alphanumeric and underscores/dashes.",
            )
        if not (isinstance(spec.input_model, type) and issubclass(spec.input_model, BaseModel)):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' operation '{spec.name}' input_model must be a BaseModel subclass",
            )
        if not (isinstance(spec.output_model, type) and issubclass(spec.output_model, BaseModel)):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' operation '{spec.name}' output_model must be a BaseModel subclass",
            )
        if not callable(spec.handler):
            raise DlcError(
                DlcErrorCode.REGISTRATION_CONFLICT,
                f"DLC '{self._staging.dlc_id}' operation '{spec.name}' handler must be callable",
            )
        for existing in self._staging.operations:
            if existing.name == spec.name:
                raise DlcError(
                    DlcErrorCode.REGISTRATION_CONFLICT,
                    f"DLC '{self._staging.dlc_id}' registered duplicate operation '{spec.name}'",
                )
        self._staging.operations.append(spec)


class DefaultBackendExtensionHost(IBackendExtensionHost):
    """Concrete implementation of BackendExtensionHost passed to DLC register(host)."""

    def __init__(self, staging: StagedDlcContributions) -> None:
        self._tools_host = _StagedToolsHost(staging)
        self._resources_host = _StagedResourcesHost(staging)
        self._context_host = _StagedContextHost(staging)
        self._artifacts_host = _StagedArtifactsHost(staging)
        self._operations_host = _StagedOperationsHost(staging)

    @property
    def tools(self) -> IExtensionToolsHost:
        return self._tools_host

    @property
    def resources(self) -> IExtensionResourcesHost:
        return self._resources_host

    @property
    def context(self) -> IExtensionContextHost:
        return self._context_host

    @property
    def artifacts(self) -> IExtensionArtifactsHost:
        return self._artifacts_host

    @property
    def operations(self) -> IExtensionOperationsHost:
        return self._operations_host
