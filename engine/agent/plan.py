"""Versioned, dynamic Task Plan shown as product progress rather than a graph."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanStepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class PlanStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=240)
    status: PlanStepStatus
    evidence_required: bool = False
    artifact_ids: list[str] = Field(default_factory=list, max_length=12)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_evidence(self) -> "PlanStep":
        if self.status is PlanStepStatus.COMPLETED and self.evidence_required and not self.artifact_ids:
            raise ValueError("A completed evidence-required step must reference at least one Artifact")
        return self


class TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    run_id: str
    turn_id: str
    version: int = Field(ge=1)
    objective: str = Field(min_length=1, max_length=1_000)
    steps: list[PlanStep] = Field(min_length=1, max_length=12)
    status: PlanStatus
    summary: str | None = Field(default=None, max_length=1_000)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_steps(self) -> "TaskPlan":
        ids = [step.id for step in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("Task Plan step IDs must be unique")
        if sum(step.status is PlanStepStatus.IN_PROGRESS for step in self.steps) > 1:
            raise ValueError("Task Plan can have at most one in-progress step")
        return self
