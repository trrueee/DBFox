"""Portable trial outcome emitted by every benchmark family."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TrialOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_id: str
    case_id: str
    repetition: int = Field(ge=1)
    verdict: Literal["pass", "fail", "unscored"]
    metrics: dict[str, float] = Field(default_factory=dict)
    failed_checks: tuple[str, ...] = ()
    evidence: dict[str, Any] = Field(default_factory=dict)
