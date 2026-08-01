from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.session import DeliveryMode


class ConversationCreateRequest(BaseModel):
    datasource_id: str
    title: str | None = None
    context_tables: list[str] = Field(default_factory=list)


class ConversationPatchRequest(BaseModel):
    title: str | None = None
    context_tables: list[str] | None = None
    archived: bool | None = None


class ConversationInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str = Field(min_length=8, max_length=256)
    delivery_mode: DeliveryMode = DeliveryMode.QUEUE
    selected_artifact_ids: list[str] = Field(default_factory=list, max_length=20)
    workspace_context: dict[str, object] = Field(default_factory=dict)
    llm_credential_id: str = Field(min_length=1, max_length=256)
    api_base: str | None = Field(default=None, max_length=2048)
    model_name: str | None = Field(default=None, max_length=256)


class ArtifactSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=256)


class ApprovalResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    decision: str = Field(pattern="^(approve|reject)$")
    note: str | None = Field(default=None, max_length=2_000)


class QuestionResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=0)
    selected_value: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=20_000)
