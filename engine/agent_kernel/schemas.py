from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class PlanStep(BaseModel):
    id: str
    title: str
    status: Literal[
        "pending",
        "running",
        "completed",
        "failed",
        "skipped",
        "waiting_approval",
    ] = "pending"
    tool_name: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class PlanState(BaseModel):
    version: str = "agent-plan/v1"
    steps: list[PlanStep] = Field(default_factory=list)


class PlanPatch(BaseModel):
    operation: Literal[
        "create_plan",
        "add_step",
        "update_step",
        "mark_running",
        "mark_completed",
        "mark_failed",
        "complete_step",
        "fail_step",
        "skip_step",
        "clear_plan",
    ]
    step: PlanStep | None = None
    step_id: str | None = None
    reason: str | None = None


class ToolCallDecision(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str


class AgentDecision(BaseModel):
    action: Literal[
        "call_tool",
        "update_plan",
        "ask_user",
        "final_answer",
        "pause",
        "wait_approval",
    ]

    tool_call: ToolCallDecision | None = None
    plan_patches: list[PlanPatch] = Field(default_factory=list)

    user_message: str | None = None
    final_answer: str | None = None

    confidence: Literal["low", "medium", "high"] = "medium"
    reasoning_summary: str = Field(
        description="Short non-sensitive explanation of why this action is next."
    )

    @model_validator(mode="after")
    def _validate_tool_call(self) -> AgentDecision:
        if self.action == "call_tool" and self.tool_call is None:
            raise ValueError("tool_call is required when action is call_tool.")
        return self
