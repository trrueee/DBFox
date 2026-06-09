from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

class PlanStep(BaseModel):
    id: str
    tool_name: str
    purpose: str | None = None
    title: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    status: Literal["pending", "running", "completed", "failed", "waiting_approval"] = "pending"
    attempt_count: int = 0
    max_attempts: int = 3
    expected_outputs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    error: str | None = None
    recovery_hint: str | None = None

class AgentPlan(BaseModel):
    id: str
    goal: str
    mode: str = "normal"
    status: Literal["created", "in_progress", "completed", "failed"] = "created"
    steps: list[PlanStep] = Field(default_factory=list)
    stop_condition: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)

class ReflectDecision(BaseModel):
    decision: Literal["continue", "replan", "retry", "revise", "ask_user", "approval", "answer", "fail"]
    reason: str
    next_step_id: str | None = None
    plan_patches: list[dict[str, Any]] = Field(default_factory=list)
    user_message: str | None = None
    confidence: float = 1.0
