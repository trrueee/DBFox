from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class AgentRuntimeEventType:
    RUN_STARTED = "agent.run.started"
    STEP_STARTED = "agent.step.started"
    STEP_COMPLETED = "agent.step.completed"
    PROGRESS_UPDATE = "agent.progress.update"
    CONTEXT_UPDATE = "agent.context.update"
    ARTIFACT_CREATED = "agent.artifact.created"
    ANSWER_COMPLETED = "agent.answer.completed"
    RUN_COMPLETED = "agent.run.completed"
    RUN_FAILED = "agent.run.failed"
    APPROVAL_REQUIRED = "agent.approval.required"
    APPROVAL_RESOLVED = "agent.approval.resolved"
    CHECKPOINT_SAVED = "agent.checkpoint.saved"
    RUN_WAITING_APPROVAL = "agent.run.waiting_approval"
    RUN_RESUMED = "agent.run.resumed"
    MODEL_STARTED = "agent.model.started"
    MODEL_COMPLETED = "agent.model.completed"
    TOOL_STARTED = "agent.tool.started"
    TOOL_COMPLETED = "agent.tool.completed"
    POLICY_ALLOWED = "agent.policy.allowed"
    POLICY_BLOCKED = "agent.policy.blocked"
    OBSERVE_APPLIED = "agent.observe.applied"
    FINALIZED = "agent.finalized"


class AgentRuntimeEvent(BaseModel):
    event_id: str
    run_id: str
    sequence: int
    created_at_ms: int
    type: str
    step: dict[str, Any] | None = None
    artifact: dict[str, Any] | None = None
    answer: dict[str, Any] | None = None
    response: Any | None = None
    approval: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None
    error: str | None = None
    approval_context: dict[str, Any] | None = None


class RuntimeConfig(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    model_name: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    execute: bool = True
    max_steps: int = 20
    db: Any = Field(default=None, exclude=True)
    registry: Any = Field(default=None, exclude=True)
