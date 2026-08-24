"""Versioned contracts for Core AuthorityBench scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuthorityCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    authorized_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    requested_id: str = Field(min_length=1, max_length=128)
    expect_access: bool

    @model_validator(mode="after")
    def validate_expectation(self) -> "AuthorityCase":
        if self.expect_access != (self.requested_id in self.authorized_ids):
            raise ValueError("expect_access must match membership in authorized_ids")
        if len(self.authorized_ids) != len(set(self.authorized_ids)):
            raise ValueError("authorized_ids must be unique")
        return self


class AuthorityDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    cases: tuple[AuthorityCase, ...] = Field(min_length=1)


def load_cases(path: Path) -> AuthorityDataset:
    return AuthorityDataset.model_validate_json(path.read_text(encoding="utf-8"))
