"""Data models for checkpoint / replay / fork operations."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class AgentCheckpointSnapshot(BaseModel):
    checkpoint_id: str
    thread_id: str
    run_id: str
    created_at: str = ""
    step: int = 0
    next_nodes: list[str] = Field(default_factory=list)
    node_writes: dict[str, Any] | None = None
    has_interrupt: bool = False
    state_summary: dict[str, Any] = Field(default_factory=dict)


class CheckpointListResponse(BaseModel):
    run_id: str
    thread_id: str
    checkpoints: list[AgentCheckpointSnapshot] = Field(default_factory=list)
    total: int = 0


class ReplayRequest(BaseModel):
    checkpoint_id: str
    run_id: str | None = None


class ReplayResponse(BaseModel):
    run_id: str
    original_run_id: str
    checkpoint_id: str
    replay_from_step: int


class ForkRequest(BaseModel):
    checkpoint_id: str
    new_question: str | None = None
    state_overrides: dict[str, Any] = Field(default_factory=dict)


class ForkResponse(BaseModel):
    new_run_id: str
    original_run_id: str
    forked_from_checkpoint_id: str
    original_step: int
