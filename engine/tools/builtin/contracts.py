from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from engine.agent.plan import PlanStep, PlanStepStatus
from engine.tools.runtime import ToolInputModel, ToolOutputModel


class EmptyInput(ToolInputModel):
    """This function takes no arguments."""


class AcknowledgementOutput(ToolOutputModel):
    acknowledged: bool = True


ConversationRole = Literal["user", "assistant"]


class ConversationSearchInput(ToolInputModel):
    query: str = Field(
        min_length=1,
        max_length=500,
        description="A literal phrase remembered from the current conversation.",
    )
    roles: list[ConversationRole] = Field(
        default_factory=lambda: ["user", "assistant"],
        min_length=1,
        max_length=2,
    )
    limit: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="after")
    def normalize_search(self) -> "ConversationSearchInput":
        query = self.query.strip()
        if not query:
            raise ValueError("Conversation search query must not be blank")
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("Conversation search roles must be unique")
        object.__setattr__(self, "query", query)
        return self


class ConversationSearchMatch(ToolOutputModel):
    message_id: str
    sequence: int = Field(ge=1)
    role: ConversationRole
    created_at: str
    snippet: str = Field(max_length=700)


class ConversationSearchOutput(ToolOutputModel):
    query: str
    searched_roles: list[ConversationRole]
    search_mode: Literal["fts5_trigram", "literal_scan"]
    matches: list[ConversationSearchMatch]
    returned_count: int = Field(ge=0)


class ConversationReadInput(ToolInputModel):
    after_sequence: int = Field(
        default=0,
        ge=0,
        description="Return messages after this sequence; use 0 for the beginning.",
    )
    limit: int = Field(default=10, ge=1, le=10)


class ConversationMessageOutput(ToolOutputModel):
    message_id: str
    sequence: int = Field(ge=1)
    role: ConversationRole
    created_at: str
    content: str = Field(max_length=4_000)
    truncated: bool


class ConversationReadOutput(ToolOutputModel):
    messages: list[ConversationMessageOutput]
    returned_count: int = Field(ge=0)
    has_more: bool
    next_after_sequence: int | None = Field(default=None, ge=1)


class ClarificationOption(ToolInputModel):
    value: str = Field(min_length=1, max_length=500)
    label: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=1_000)


class RequestClarificationInput(ToolInputModel):
    question: str = Field(min_length=1, max_length=4_000)
    reason: str = Field(min_length=1, max_length=2_000)
    options: list[ClarificationOption] = Field(default_factory=list, max_length=12)
    allow_free_text: bool = True


class UpdatePlanInput(ToolInputModel):
    objective: str = Field(min_length=1, max_length=1_000)
    steps: list[PlanStep] = Field(min_length=1, max_length=12)
    summary: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def validate_plan_shape(self) -> "UpdatePlanInput":
        ids = [step.id for step in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("Plan step IDs must be unique")
        if sum(step.status is PlanStepStatus.IN_PROGRESS for step in self.steps) > 1:
            raise ValueError("Plan can have at most one in-progress step")
        return self


class UpdatePlanOutput(ToolOutputModel):
    plan_id: str
    version: int = Field(ge=1)
    objective: str
    steps: list[PlanStep]
    status: str
    summary: str | None = None
