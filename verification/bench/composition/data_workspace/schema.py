"""Case contracts owned by the Data + Workspace CompositionBench."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DataWorkspaceCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    prompt: str = Field(min_length=1, max_length=2_000)
    workspace_file: str = Field(min_length=1, max_length=240)
    workspace_content: str = Field(min_length=1, max_length=4_000)
    required_answer_terms: tuple[str, ...] = Field(min_length=1)
    required_tools: tuple[str, ...] = Field(min_length=2)
    max_turns: int = Field(ge=1, le=10)
    max_tool_calls: int = Field(ge=1, le=10)


class DataWorkspaceDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    cases: tuple[DataWorkspaceCase, ...] = Field(min_length=1)


def load_cases(path: Path) -> DataWorkspaceDataset:
    return DataWorkspaceDataset.model_validate_json(path.read_text(encoding="utf-8"))
