"""Durable ToolInvocation contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engine.tools.materialization import ToolRecoveryPolicy


class ToolInvocationStatus(StrEnum):
    REQUESTED = "requested"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ToolInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    session_id: str
    run_id: str
    turn_id: str
    provider_call_id: str
    tool_name: str
    tool_version: str
    authorized_input: dict[str, Any]
    authorized_input_hash: str
    idempotency_key: str
    status: ToolInvocationStatus
    policy: dict[str, Any] = Field(default_factory=dict)
    recovery_policy: ToolRecoveryPolicy
    attempt_count: int = 0
