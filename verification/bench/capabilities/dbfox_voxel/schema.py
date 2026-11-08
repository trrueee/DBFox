"""Voxel case contracts; no domain scorer leaks into the shared framework."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    kind: Literal["tool", "human", "answer"] = "tool"
    tool: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    text: str = ""
    succeeds: bool = True
    unchanged: bool = False
    error_contains: str = ""


class VoxelCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    category: str
    prompt: str
    steps: tuple[Step, ...]
    nonzero_count: int | None = None
    min_nonzero_count: int = 0
    points: tuple[dict[str, Any], ...] = ()
    assertions: dict[str, Any] = Field(default_factory=dict)
    stress: bool = False

    @model_validator(mode="after")
    def unique_steps(self) -> "VoxelCase":
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Voxel step identities must be unique")
        return self


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    cases: tuple[VoxelCase, ...]


def load_cases(path: Path) -> Dataset:
    return Dataset.model_validate_json(path.read_text(encoding="utf-8"))
