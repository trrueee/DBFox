"""User-visible Agent work products and their immutable relationships."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArtifactType(StrEnum):
    ANALYSIS_PLAN = "analysis_plan"
    SQL = "sql"
    SAFETY = "safety"
    RESULT_VIEW = "result_view"
    CHART = "chart"
    MARKDOWN = "markdown"
    ERROR = "error"


class ArtifactStatus(StrEnum):
    CREATING = "creating"
    COMPLETED = "completed"
    FAILED = "failed"
    STALE = "stale"


class ArtifactRelationType(StrEnum):
    VALIDATED_BY = "validated_by"
    EXECUTED_AS = "executed_as"
    VISUALIZED_AS = "visualized_as"
    DERIVED_FROM = "derived_from"
    SUPPORTS = "supports"


class ArtifactRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation: ArtifactRelationType
    artifact_id: str


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    session_id: str
    run_id: str
    turn_id: str | None = None
    type: ArtifactType
    title: str
    semantic_key: str | None = None
    version: int = Field(default=1, ge=1)
    status: ArtifactStatus = ArtifactStatus.COMPLETED
    summary: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_ref: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    relations: list[ArtifactRelation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_relations(self) -> "Artifact":
        if any(relation.artifact_id == self.id for relation in self.relations):
            raise ValueError("Artifact cannot relate to itself")
        return self


class ArtifactSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    artifact_id: str
    selected_by: str
    reason: str | None = None


class ArtifactSelectionSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    reason: str
    replace_automatic_selection: bool = True
