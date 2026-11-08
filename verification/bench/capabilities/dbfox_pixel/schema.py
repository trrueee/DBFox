"""Pixel-owned scenarios; the shared benchmark schema has no drawing semantics."""
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
    # A pixel-writing step must preserve all cells outside these explicit rectangles.
    allowed_changes: list[dict[str, Any]] | None = None


class PixelCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    category: str
    prompt: str
    clarification: str = ""
    steps: tuple[Step, ...]
    assertions: dict[str, Any] = Field(default_factory=dict)
    stress: bool = False

    @model_validator(mode="after")
    def unique_steps(self):
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Pixel step IDs must be unique")
        return self


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    cases: tuple[PixelCase, ...]


def load_cases(path: Path) -> Dataset:
    return Dataset.model_validate_json(path.read_text(encoding="utf-8"))
