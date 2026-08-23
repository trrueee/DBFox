from __future__ import annotations

from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from engine.tools.runtime.attempt import ResourceKey, ResourceScopeRef
from sqlalchemy.orm import Session

from engine.agent.artifact import Artifact, ArtifactRelationType


class ToolInvocationRequest(Protocol):
    question: str
    session_id: str
    run_id: str
    turn_id: str
    execution_id: str

class ToolRunContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str = ""
    tool_name: str = ""
    invocation_id: str = ""
    idempotency_key: str
    raw_input: Mapping[str, Any] = Field(default_factory=dict)
    request: Any | None = Field(default=None, exclude=True)
    cancellation_probe: Callable[[], bool] | None = Field(default=None, exclude=True)
    deadline: float | None = Field(default=None, exclude=True)
    execution_authority: Any | None = Field(default=None, exclude=True)
    scope_refs: tuple[ResourceScopeRef, ...] = ()
    resolved_resources: Mapping[ResourceKey, Any] = Field(default_factory=dict, exclude=True)
    metadata_session: Session | None = Field(default=None, exclude=True)
    artifact_loader: Callable[[str], Artifact | None] | None = Field(
        default=None,
        exclude=True,
    )
    artifact_relation_loader: Callable[
        [str, ArtifactRelationType],
        tuple[Artifact, ...],
    ] | None = Field(default=None, exclude=True)

    def is_cancelled(self) -> bool:
        return bool(self.cancellation_probe and self.cancellation_probe())

    def resource(self, ref: ResourceScopeRef | ResourceKey) -> Any:
        key = ref.canonical() if isinstance(ref, ResourceScopeRef) else ref
        if key not in self.resolved_resources:
            raise RuntimeError(
                f"This tool is not authorized for execution resource {key!r}"
            )
        return self.resolved_resources[key]

    def resources(self, kind: str) -> tuple[Any, ...]:
        return tuple(
            resource
            for (resource_kind, _resource_id), resource in self.resolved_resources.items()
            if resource_kind == kind
        )

    def require_one(self, kind: str) -> Any:
        matches = self.resources(kind)
        if not matches:
            raise RuntimeError(f"This tool requires the {kind!r} execution resource")
        if len(matches) > 1:
            raise RuntimeError(
                f"This tool requires exactly one {kind!r} execution resource; "
                "select one by resource id"
            )
        return matches[0]

    def scopes(self, kind: str) -> tuple[ResourceScopeRef, ...]:
        return tuple(ref for ref in self.scope_refs if ref.kind == kind)

    def scope(self, kind: str, resource_id: str | None = None) -> ResourceScopeRef | None:
        matches = self.scopes(kind)
        if resource_id is not None:
            return next((ref for ref in matches if ref.id == resource_id), None)
        if len(matches) > 1:
            raise RuntimeError(
                f"Resource kind {kind!r} is ambiguous; select a resource by (kind, id)"
            )
        return matches[0] if matches else None

    def require_metadata(self) -> Session:
        if self.metadata_session is None:
            raise RuntimeError("This tool requires the core metadata session")
        return self.metadata_session

    def require_request(self) -> ToolInvocationRequest:
        if self.request is None:
            raise RuntimeError("This tool requires an agent invocation request")
        return cast(ToolInvocationRequest, self.request)

    def artifact(self, artifact_id: str) -> Artifact:
        """Load one immutable Artifact scoped to the current invoking Run."""

        normalized = str(artifact_id).strip()
        if not normalized or self.artifact_loader is None:
            raise RuntimeError("This tool cannot access the requested Artifact")
        artifact = self.artifact_loader(normalized)
        if artifact is None:
            raise RuntimeError("The requested Artifact is unavailable in this Run")
        return artifact

    def artifacts_relating_to(
        self,
        artifact_id: str,
        relation: ArtifactRelationType,
    ) -> tuple[Artifact, ...]:
        normalized = str(artifact_id).strip()
        if not normalized or self.artifact_relation_loader is None:
            return ()
        return self.artifact_relation_loader(normalized, relation)

    def approval_authorizes(
        self,
        approval_subject: dict[str, Any],
        resource_ref: ResourceScopeRef | None,
    ) -> bool:
        authorizes = getattr(self.execution_authority, "authorizes", None)
        return bool(
            callable(authorizes)
            and authorizes(
                tool_name=self.tool_name,
                approval_subject=approval_subject,
                resource_ref=resource_ref,
            )
        )

    @classmethod
    def for_invocation(
        cls,
        *,
        request: Any | None,
        tool_name: str = "",
        invocation_id: str = "",
        idempotency_key: str,
        raw_input: dict[str, Any] | None = None,
        cancellation_probe: Callable[[], bool] | None = None,
        deadline: float | None = None,
        execution_authority: Any | None = None,
        scope_refs: tuple[ResourceScopeRef, ...] | None = None,
        resources: Mapping[ResourceKey, Any] | None = None,
        metadata_session: Session | None = None,
        artifact_loader: Callable[[str], Artifact | None] | None = None,
        artifact_relation_loader: Callable[
            [str, ArtifactRelationType],
            tuple[Artifact, ...],
        ] | None = None,
    ) -> "ToolRunContext":
        thread_id = str(getattr(request, "session_id", "") or "")
        return cls(
            thread_id=thread_id,
            tool_name=tool_name,
            invocation_id=invocation_id,
            idempotency_key=idempotency_key,
            raw_input=MappingProxyType(dict(raw_input or {})),
            request=request,
            cancellation_probe=cancellation_probe,
            deadline=deadline,
            execution_authority=execution_authority,
            scope_refs=scope_refs or (),
            resolved_resources=dict(resources or {}),
            metadata_session=metadata_session,
            artifact_loader=artifact_loader,
            artifact_relation_loader=artifact_relation_loader,
        )


