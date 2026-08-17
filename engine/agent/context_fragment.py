"""Minimal Kernel-owned Context fragment seam.

Only the Kernel defines lanes/budgets and wraps fragments as untrusted data.
Contributors return bounded text plus provenance; they never choose roles,
priorities or Provider wire format.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue


ContextLane = Literal["working_state", "resource", "evidence"]

MAX_CONTEXT_FRAGMENT_CHARS = 4_000
MAX_CONTEXT_FRAGMENTS_PER_CONTRIBUTOR = 8


class ContextFragment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    source_version: str
    lane: ContextLane
    content: str = Field(max_length=MAX_CONTEXT_FRAGMENT_CHARS)
    provenance: dict[str, JsonValue] = Field(default_factory=dict)


class ContextContributionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    run_id: str
    current_request: str
    workspace_id: str | None = None
    workspace_version: str | None = None


class ContextContributor(Protocol):
    id: str

    def build(
        self,
        input: ContextContributionInput,
    ) -> tuple[ContextFragment, ...]: ...
