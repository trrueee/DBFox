from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MusicDirectCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    scenario: Literal["revision_immutability", "transpose", "edit_locality", "score_validity"]


class MusicDirectDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    cases: tuple[MusicDirectCase, ...] = Field(min_length=1)


def load_cases(path: Path) -> MusicDirectDataset:
    return MusicDirectDataset.model_validate_json(path.read_text(encoding="utf-8"))
