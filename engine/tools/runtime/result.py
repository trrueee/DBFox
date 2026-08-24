"""Provider-neutral result returned by a tool leaf."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.agent.artifact import ArtifactDraft


O = TypeVar("O", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ToolOutcome(Generic[O]):
    """Typed tool output plus generic Artifact drafts to persist atomically."""

    output: O
    artifacts: tuple[ArtifactDraft, ...] = ()


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["success", "failed"]
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    artifact_drafts: list[ArtifactDraft] = Field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    latency_ms: int
    attempts: int = 1


class ToolReconciliation(BaseModel):
    """Result of looking up an interrupted external action by idempotency key."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["succeeded", "not_applied", "failed", "unknown"]
    output: dict[str, Any] | None = None
    artifacts: tuple[ArtifactDraft, ...] = ()
    error: str | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "ToolReconciliation":
        if self.status == "succeeded" and self.output is None:
            raise ValueError("A succeeded reconciliation must include output")
        if self.status != "succeeded" and self.output is not None:
            raise ValueError("Only a succeeded reconciliation may include output")
        if self.status != "succeeded" and self.artifacts:
            raise ValueError("Only a succeeded reconciliation may include Artifacts")
        if self.status != "failed" and self.error_code is not None:
            raise ValueError("Only a failed reconciliation may include an error_code")
        return self
