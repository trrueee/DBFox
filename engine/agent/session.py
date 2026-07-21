"""Session aggregate contracts for admitted user input and durable ownership."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DeliveryMode(StrEnum):
    QUEUE = "queue"
    STEER = "steer"
    CANCEL_AND_REPLACE = "cancel_and_replace"
    RESPOND = "respond"


class SessionInputStatus(StrEnum):
    ADMITTED = "admitted"
    PROMOTED = "promoted"
    CONSUMED = "consumed"
    CANCELLED = "cancelled"


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    session_id: str
    sequence: int = Field(ge=1)
    idempotency_key: str
    content: str
    delivery_mode: DeliveryMode = DeliveryMode.QUEUE
    selected_artifact_ids: list[str] = Field(default_factory=list)
    workspace_context: dict[str, object] = Field(default_factory=dict)
    reply_to_request_id: str | None = None
    status: SessionInputStatus = SessionInputStatus.ADMITTED
    admitted_at: datetime


class SessionLease(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    owner: str
    token: int = Field(ge=1)
    expires_at: datetime
