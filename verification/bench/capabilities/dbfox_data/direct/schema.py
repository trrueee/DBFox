"""Case contracts owned by the direct Data capability benchmark."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DataDirectCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    scenario: Literal["resource_discovery", "catalog_refresh", "catalog_browse"]
    expected_tables: tuple[str, ...] = Field(min_length=1)


class DataDirectDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    cases: tuple[DataDirectCase, ...] = Field(min_length=1)


def load_cases(path: Path) -> DataDirectDataset:
    return DataDirectDataset.model_validate_json(path.read_text(encoding="utf-8"))
