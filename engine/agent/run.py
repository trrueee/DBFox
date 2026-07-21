"""Run aggregate state and deterministic execution limits."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_RUN_STATUSES = frozenset({RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.FAILED})


class RunLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_turns: int = Field(default=24, ge=1, le=100)
    max_tool_invocations: int = Field(default=48, ge=1, le=200)
    max_repair_attempts: int = Field(default=4, ge=0, le=20)
    max_provider_retries: int = Field(default=2, ge=0, le=10)
    max_stalled_turns: int = Field(default=2, ge=1, le=10)
    timeout_seconds: int = Field(default=900, ge=10, le=7200)
    token_budget: int | None = Field(default=None, ge=1)
    cost_budget_usd: float | None = Field(default=None, gt=0)


class RunConflict(RuntimeError):
    pass


class SessionLeaseConflict(RunConflict):
    pass
