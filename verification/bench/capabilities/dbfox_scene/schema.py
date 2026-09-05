"""Scene case contracts; no domain scorer leaks into the shared framework."""
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


class SceneCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    category: str
    prompt: str
    steps: tuple[Step, ...]
    object_count: int = 0
    material_count: int = 0
    assertions: dict[str, Any] = Field(default_factory=dict)
    stress: bool = False

    @model_validator(mode="after")
    def unique_steps(self) -> "SceneCase":
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Scene step identities must be unique")
        return self


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    cases: tuple[SceneCase, ...]


def load_cases(path: Path) -> Dataset:
    return Dataset.model_validate_json(path.read_text(encoding="utf-8"))
