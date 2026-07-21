"""Durable business clarification contract.

Questions collect missing information.  They never authorize a tool action;
authorization remains exclusively in the Approval domain.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuestionStatus(StrEnum):
    PENDING = "pending"
    ANSWERED = "answered"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class QuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str = Field(min_length=1, max_length=500)
    label: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=1_000)


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    session_id: str
    run_id: str
    turn_id: str
    status: QuestionStatus
    version: int = Field(ge=0)
    question: str = Field(min_length=1, max_length=4_000)
    reason: str = Field(min_length=1, max_length=2_000)
    options: list[QuestionOption] = Field(default_factory=list, max_length=12)
    allow_free_text: bool = True
    response: dict[str, Any] | None = None
    expires_at: datetime | None = None


class QuestionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    selected_value: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def require_value(self) -> "QuestionAnswer":
        if not self.selected_value and not self.text:
            raise ValueError("A question response requires a selected option or text")
        return self


class QuestionConflict(RuntimeError):
    pass
