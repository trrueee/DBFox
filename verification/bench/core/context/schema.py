"""Versioned contracts for Core ContextBench scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContextCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    scenario: Literal["current_request_priority", "long_recall"]
    prompt: str = Field(min_length=1, max_length=2_000)
    history_count: int = Field(ge=1, le=200)
    fact: str = Field(min_length=1, max_length=2_000)
    sensitive_term: str = Field(min_length=1, max_length=200)
    required_answer_terms: tuple[str, ...] = Field(min_length=1)
    max_turns: int = Field(ge=1, le=20)
    max_tool_calls: int = Field(ge=0, le=20)


class ContextDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    cases: tuple[ContextCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> "ContextDataset":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("ContextBench case_id values must be unique")
        return self


def load_cases(path: Path) -> ContextDataset:
    return ContextDataset.model_validate_json(path.read_text(encoding="utf-8"))
