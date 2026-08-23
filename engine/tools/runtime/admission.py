"""Provider-neutral validation seam evaluated before a Tool attempt."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from engine.agent.artifact import Artifact, ArtifactRelationType
from engine.json_codec import byte_size
from engine.tools.runtime.attempt import ResourceScopeRef


MAX_ADMISSION_SUBJECT_BYTES = 32_768


class ToolAdmissionDecision(BaseModel):
    """A domain validation verdict; final authority remains Kernel-owned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["allowed", "blocked", "approval_required"]
    reason: str = Field(min_length=1, max_length=512)
    risk_level: Literal["safe", "warning", "danger"] = "safe"
    approval_subject: dict[str, JsonValue] | None = None
    resource_ref: ResourceScopeRef | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> "ToolAdmissionDecision":
        if self.status == "approval_required" and self.approval_subject is None:
            raise ValueError("approval_required admission needs an approval_subject")
        if self.status != "approval_required" and self.approval_subject is not None:
            raise ValueError("Only approval_required admission may expose a subject")
        if (
            self.approval_subject is not None
            and byte_size(self.approval_subject) > MAX_ADMISSION_SUBJECT_BYTES
        ):
            raise ValueError("Tool admission subject exceeds its bounded limit")
        return self


ArtifactLoader = Callable[[str], Artifact | None]
ArtifactRelationLoader = Callable[
    [str, ArtifactRelationType],
    tuple[Artifact, ...],
]


@dataclass(frozen=True, slots=True)
class ToolAdmissionContext:
    """Read-only current-Run facts available to a Tool admission hook."""

    session_id: str
    run_id: str
    resource_refs: tuple[ResourceScopeRef, ...]
    artifact_loader: ArtifactLoader
    artifact_relation_loader: ArtifactRelationLoader

    def scopes(self, kind: str) -> tuple[ResourceScopeRef, ...]:
        return tuple(ref for ref in self.resource_refs if ref.kind == kind)

    def artifact(self, artifact_id: str) -> Artifact:
        normalized = str(artifact_id).strip()
        artifact = self.artifact_loader(normalized) if normalized else None
        if artifact is None:
            raise RuntimeError("The requested Artifact is unavailable in this Run")
        return artifact

    def artifacts_relating_to(
        self,
        artifact_id: str,
        relation: ArtifactRelationType,
    ) -> tuple[Artifact, ...]:
        normalized = str(artifact_id).strip()
        if not normalized:
            return ()
        return self.artifact_relation_loader(normalized, relation)
