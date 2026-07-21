"""Durable human authorization contract."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    session_id: str
    run_id: str
    turn_id: str
    tool_invocation_id: str
    tool_name: str
    status: ApprovalStatus
    version: int = Field(ge=0)
    risk_level: str
    reason: str
    policy_decision: dict[str, Any]
    requested_action: dict[str, Any]
    created_at: datetime | None = None
    expires_at: datetime | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_note: str | None = None


class ApprovalConflict(RuntimeError):
    pass
