"""Versioned scripted case contracts for the capability-neutral Core Loop suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScriptStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["answer", "tool"]
    content: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self) -> "ScriptStep":
        if self.kind == "answer" and not self.content.strip():
            raise ValueError("Answer steps require content")
        if self.kind == "tool" and not self.tool_name.strip():
            raise ValueError("Tool steps require tool_name")
        return self


class CoreLoopCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    prompt: str = Field(min_length=1, max_length=2_000)
    steps: tuple[ScriptStep, ...] = Field(min_length=1)
    required_answer_terms: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    max_turns: int = Field(ge=1)
    max_tool_calls: int = Field(ge=0)


class CoreLoopDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    cases: tuple[CoreLoopCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> "CoreLoopDataset":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Core Loop case_id values must be unique")
        return self


def load_cases(path: Path) -> CoreLoopDataset:
    return CoreLoopDataset.model_validate_json(path.read_text(encoding="utf-8"))
