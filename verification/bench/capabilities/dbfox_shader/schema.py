"""Suite-owned expectations; no shader concepts enter the shared bench framework."""
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
    # Compare the complete canonical before/after, excluding only these object IDs
    # or document fields. Unmentioned source and configuration must remain exact.
    allowed_objects: tuple[str, ...] = ()
    allowed_fields: tuple[str, ...] = ()
    checks: tuple[dict[str, Any], ...] = ()


class ShaderCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    category: str
    prompt: str
    clarification: str = ""
    steps: tuple[Step, ...]
    assertions: tuple[dict[str, Any], ...] = ()
    stress: bool = False

    @model_validator(mode="after")
    def unique_steps(self):
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Shader step IDs must be unique")
        return self


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    cases: tuple[ShaderCase, ...]

    @model_validator(mode="after")
    def unique_cases(self):
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Shader case IDs must be unique")
        return self


def load_cases(path: Path) -> Dataset:
    return Dataset.model_validate_json(path.read_text(encoding="utf-8"))
