from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CoreMusicCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    prompt: str
    title: str
    measure_count: int = Field(ge=1, le=32)
    max_turns: int = Field(ge=1, le=6)
    max_tool_calls: int = Field(ge=1, le=4)


class CoreMusicDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    cases: tuple[CoreMusicCase, ...] = Field(min_length=1)


def load_cases(path: Path) -> CoreMusicDataset:
    return CoreMusicDataset.model_validate_json(path.read_text(encoding="utf-8"))
