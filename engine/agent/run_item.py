"""Canonical public projection for every user-visible Agent Run item."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.plan import PlanStep
from engine.agent.response import CompletionDisposition, CompletionLimitationCode
from engine.json_codec import load_array, load_object
from engine.tools.runtime.base import RiskLevel, ToolPresentation


class RunItemType(StrEnum):
    MESSAGE = "message"
    PLAN = "plan"
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"
    APPROVAL = "approval"
    QUESTION = "question"


class RunItemStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    label: str | None = None


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    claim_id: str
    artifact_id: str
    label: str
    query_fingerprint: str
    observed_at: datetime
    locator: dict[str, Any] = Field(default_factory=dict)
    value: Any | None = None


class MessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    phase: Literal["commentary", "final_answer"] | None = None
    content: str = ""
    evidence: list[EvidenceReference] = Field(default_factory=list)
    artifact_refs: list[ArtifactReference] = Field(default_factory=list)
    completion_disposition: CompletionDisposition | None = None
    limitation_codes: list[CompletionLimitationCode] = Field(default_factory=list)


class PlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str
    steps: list[PlanStep] = Field(default_factory=list)
    summary: str | None = None


class FunctionCallPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    name: str
    tool_version: str
    presentation: ToolPresentation
    arguments: dict[str, Any] = Field(default_factory=dict)
    attempt: int = Field(default=0, ge=0)


class FunctionCallOutputPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    output: str = ""
    summary: str = ""
    artifact_refs: list[ArtifactReference] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class ApprovalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)
    tool_invocation_id: str | None = None
    risk_level: RiskLevel
    reason: str | None = None
    requested_action: dict[str, Any] = Field(default_factory=dict)
    decision: str | None = None
    decision_note: str | None = None


class QuestionOptionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    description: str | None = None


class QuestionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)
    question: str
    reason: str
    options: list[QuestionOptionPayload] = Field(default_factory=list)
    allow_free_text: bool = True
    response: dict[str, Any] | None = None


class RunItemBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    run_id: str
    turn_id: str | None = None
    sequence: int = Field(default=0, ge=0)
    revision: int = Field(default=1, ge=1)
    status: RunItemStatus
    created_at: datetime
    completed_at: datetime | None = None


class MessageItem(RunItemBase):
    type: Literal[RunItemType.MESSAGE] = RunItemType.MESSAGE
    payload: MessagePayload


class PlanItem(RunItemBase):
    type: Literal[RunItemType.PLAN] = RunItemType.PLAN
    payload: PlanPayload


class FunctionCallItem(RunItemBase):
    type: Literal[RunItemType.FUNCTION_CALL] = RunItemType.FUNCTION_CALL
    payload: FunctionCallPayload


class FunctionCallOutputItem(RunItemBase):
    type: Literal[RunItemType.FUNCTION_CALL_OUTPUT] = RunItemType.FUNCTION_CALL_OUTPUT
    payload: FunctionCallOutputPayload


class ApprovalItem(RunItemBase):
    type: Literal[RunItemType.APPROVAL] = RunItemType.APPROVAL
    payload: ApprovalPayload


class QuestionItem(RunItemBase):
    type: Literal[RunItemType.QUESTION] = RunItemType.QUESTION
    payload: QuestionPayload


RunItem = Annotated[
    MessageItem
    | PlanItem
    | FunctionCallItem
    | FunctionCallOutputItem
    | ApprovalItem
    | QuestionItem,
    Field(discriminator="type"),
]


AgentRunStatus = Literal[
    "created",
    "queued",
    "running",
    "waiting_approval",
    "waiting_input",
    "cancelling",
    "completed",
    "failed",
    "cancelled",
]


class RunError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str


class RunProjection(BaseModel):
    """Canonical public Run state shared by snapshots and lifecycle events."""

    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    input_id: str
    session_sequence: int = Field(ge=1)
    user_message_id: str
    datasource_id: str
    question: str
    status: AgentRunStatus
    version: int = Field(ge=0)
    current_turn_id: str | None = None
    cancel_requested: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: RunError | None = None


RunItemDeltaField = Literal["content"]


class RunItemDelta(BaseModel):
    """Ephemeral append-only delta for an already-started durable RunItem."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    run_id: str
    turn_id: str | None = None
    item_id: str
    item_type: RunItemType
    field: RunItemDeltaField
    revision: int = Field(ge=1)
    offset: int = Field(ge=0)
    content: str


def dump_run_item(item: RunItem) -> dict[str, Any]:
    return item.model_dump(mode="json")


def project_run(run: Any) -> dict[str, Any]:
    """Canonical public Run state carried by every Run lifecycle event."""

    return RunProjection.model_validate({
        "id": str(run.id),
        "session_id": str(run.session_id),
        "input_id": str(run.input_id),
        "status": str(run.status),
        "version": int(run.version or 0),
        "session_sequence": int(run.session_sequence),
        "datasource_id": str(run.datasource_id),
        "question": str(run.question),
        "user_message_id": str(run.user_message_id),
        "current_turn_id": str(run.current_turn_id) if run.current_turn_id else None,
        "cancel_requested": bool(run.cancel_requested),
        "result": load_object(str(run.result_json or "{}")),
        "error": (
            RunError(code=str(run.error_code), message=str(run.error_message or ""))
            if run.error_code
            else None
        ),
    }).model_dump(mode="json")


def user_message_item(message: Any, *, run_id: str, sequence: int = 0) -> MessageItem:
    return MessageItem(
        id=str(message.id),
        session_id=str(message.session_id),
        run_id=run_id,
        sequence=sequence,
        revision=1,
        status=RunItemStatus.COMPLETED,
        created_at=message.created_at,
        completed_at=message.updated_at,
        payload=MessagePayload(role="user", content=str(message.content)),
    )


def assistant_message_item(
    message: Any,
    *,
    run: Any,
    turn_id: str | None = None,
    phase: Literal["commentary", "final_answer"],
    evidence: list[EvidenceReference] | None = None,
    artifact_refs: list[ArtifactReference] | None = None,
    sequence: int = 0,
) -> MessageItem:
    status = {
        "created": RunItemStatus.PENDING,
        "streaming": RunItemStatus.IN_PROGRESS,
        "completed": RunItemStatus.COMPLETED,
        "failed": RunItemStatus.FAILED,
        "cancelled": RunItemStatus.CANCELLED,
    }[str(message.status)]
    resolved_turn_id = turn_id or (
        str(run.current_turn_id) if run.current_turn_id else None
    )
    response = load_object(str(run.response_json or "{}"))
    completion_disposition = response.get("completion_disposition")
    limitation_codes = response.get("limitation_codes")
    return MessageItem(
        id=f"message:{run.id}:{resolved_turn_id or 'terminal'}",
        session_id=str(message.session_id),
        run_id=str(run.id),
        turn_id=resolved_turn_id,
        sequence=sequence,
        revision=max(1, int(run.version or 0) + 1),
        status=status,
        created_at=message.created_at,
        completed_at=message.updated_at if status in {
            RunItemStatus.COMPLETED,
            RunItemStatus.FAILED,
            RunItemStatus.CANCELLED,
        } else None,
        payload=MessagePayload.model_validate({
            "role": "assistant",
            "phase": phase,
            "content": str(message.content or ""),
            "evidence": evidence or [],
            "artifact_refs": artifact_refs or [],
            "completion_disposition": (
                completion_disposition
                if isinstance(completion_disposition, str)
                else None
            ),
            "limitation_codes": (
                [value for value in limitation_codes if isinstance(value, str)]
                if isinstance(limitation_codes, list)
                else []
            ),
        }),
    )


def final_answer_item(
    message: Any,
    *,
    run: Any,
    evidence: list[EvidenceReference] | None = None,
    artifact_refs: list[ArtifactReference] | None = None,
    sequence: int = 0,
) -> MessageItem:
    return assistant_message_item(
        message,
        run=run,
        phase="final_answer",
        evidence=evidence,
        artifact_refs=artifact_refs,
        sequence=sequence,
    )


def evidence_reference(evidence: Any) -> EvidenceReference:
    locator = evidence.locator.model_dump(mode="json")
    return EvidenceReference(
        id=str(evidence.id),
        claim_id=str(evidence.claim_id),
        artifact_id=str(evidence.artifact_id),
        label=str(evidence.label),
        query_fingerprint=str(evidence.query_fingerprint),
        observed_at=evidence.observed_at,
        locator=locator,
        value=evidence.value,
    )


def plan_item(plan: Any, *, sequence: int = 0) -> PlanItem:
    status = {
        "active": RunItemStatus.IN_PROGRESS,
        "blocked": RunItemStatus.WAITING,
        "completed": RunItemStatus.COMPLETED,
        "partial": RunItemStatus.COMPLETED,
        "failed": RunItemStatus.FAILED,
        "cancelled": RunItemStatus.CANCELLED,
    }[str(plan.status)]
    return PlanItem(
        id=str(plan.id),
        session_id=str(plan.session_id),
        run_id=str(plan.run_id),
        turn_id=str(plan.turn_id),
        sequence=sequence,
        revision=max(1, int(plan.version or 1)),
        status=status,
        created_at=plan.created_at,
        completed_at=plan.updated_at if status not in {
            RunItemStatus.IN_PROGRESS,
            RunItemStatus.WAITING,
        } else None,
        payload=PlanPayload.model_validate({
            "objective": str(plan.objective),
            "steps": load_array(str(plan.steps_json or "[]")),
            "summary": str(plan.summary) if plan.summary else None,
        }),
    )


def function_call_item(
    invocation: Any,
    *,
    sequence: int = 0,
) -> FunctionCallItem:
    status = {
        "requested": RunItemStatus.PENDING,
        "running": RunItemStatus.IN_PROGRESS,
        "waiting_approval": RunItemStatus.WAITING,
        "waiting_input": RunItemStatus.WAITING,
        "succeeded": RunItemStatus.COMPLETED,
        "failed": RunItemStatus.FAILED,
        "rejected": RunItemStatus.FAILED,
        "unknown": RunItemStatus.FAILED,
        "cancelled": RunItemStatus.CANCELLED,
    }[str(invocation.status)]
    presentation = ToolPresentation.model_validate_json(str(invocation.presentation_json))
    return FunctionCallItem(
        id=str(invocation.id),
        session_id=str(invocation.session_id),
        run_id=str(invocation.run_id),
        turn_id=str(invocation.turn_id),
        sequence=sequence,
        revision=max(1, int(invocation.attempt_count or 0) + 1),
        status=status,
        created_at=invocation.created_at,
        completed_at=invocation.completed_at,
        payload=FunctionCallPayload(
            call_id=str(invocation.provider_call_id),
            name=str(invocation.tool_name),
            tool_version=str(invocation.tool_version),
            presentation=presentation,
            arguments=cast(
                dict[str, Any],
                load_object(str(invocation.input_json or "{}")),
            ),
            attempt=int(invocation.attempt_count or 0),
        ),
    )


def function_call_output_item(
    invocation: Any,
    observation: Any,
    *,
    sequence: int = 0,
) -> FunctionCallOutputItem:
    artifact_ids = load_array(str(observation.artifact_ids_json or "[]"))
    failed = str(observation.status) != "succeeded"
    cancelled = str(observation.status) == "cancelled"
    return FunctionCallOutputItem(
        id=f"output:{invocation.id}",
        session_id=str(invocation.session_id),
        run_id=str(invocation.run_id),
        turn_id=str(invocation.turn_id),
        sequence=sequence,
        revision=1,
        status=(
            RunItemStatus.CANCELLED
            if cancelled
            else RunItemStatus.FAILED
            if failed
            else RunItemStatus.COMPLETED
        ),
        created_at=observation.created_at,
        completed_at=observation.created_at,
        payload=FunctionCallOutputPayload(
            call_id=str(invocation.provider_call_id),
            output=str(observation.model_output_json),
            summary=str(observation.model_visible_summary or ""),
            artifact_refs=[
                ArtifactReference(artifact_id=str(artifact_id))
                for artifact_id in artifact_ids
            ],
            error_code=str(invocation.error_code) if invocation.error_code else None,
            error_message=str(invocation.error_message) if invocation.error_message else None,
        ),
    )

def approval_item(approval: Any, *, sequence: int = 0) -> ApprovalItem:
    status = (
        RunItemStatus.WAITING
        if str(approval.status) == "pending"
        else RunItemStatus.CANCELLED
        if str(approval.status) in {"cancelled", "expired"}
        else RunItemStatus.COMPLETED
    )
    return ApprovalItem(
        id=str(approval.id),
        session_id=str(approval.session_id),
        run_id=str(approval.run_id),
        turn_id=str(approval.turn_id) if approval.turn_id else None,
        sequence=sequence,
        revision=max(1, int(approval.version or 0) + 1),
        status=status,
        created_at=approval.created_at,
        completed_at=approval.decided_at,
        payload=ApprovalPayload.model_validate({
            "version": int(approval.version or 0),
            "tool_invocation_id": (
                str(approval.tool_invocation_id)
                if approval.tool_invocation_id
                else None
            ),
            "risk_level": str(approval.risk_level),
            "reason": str(approval.reason) if approval.reason else None,
            "requested_action": cast(
                dict[str, Any],
                load_object(str(approval.requested_action_json or "{}")),
            ),
            "decision": None if str(approval.status) == "pending" else str(approval.status),
            "decision_note": str(approval.decision_note) if approval.decision_note else None,
        }),
    )


def question_item(question: Any, *, sequence: int = 0) -> QuestionItem:
    status = (
        RunItemStatus.WAITING
        if str(question.status) == "pending"
        else RunItemStatus.CANCELLED
        if str(question.status) in {"cancelled", "expired"}
        else RunItemStatus.COMPLETED
    )
    return QuestionItem(
        id=str(question.id),
        session_id=str(question.session_id),
        run_id=str(question.run_id),
        turn_id=str(question.turn_id),
        sequence=sequence,
        revision=max(1, int(question.version or 0) + 1),
        status=status,
        created_at=question.created_at,
        completed_at=question.answered_at,
        payload=QuestionPayload(
            version=int(question.version or 0),
            question=str(question.question),
            reason=str(question.reason),
            options=[
                QuestionOptionPayload.model_validate(option)
                for option in load_array(str(question.options_json or "[]"))
            ],
            allow_free_text=bool(question.allow_free_text),
            response=(
                cast(
                    dict[str, Any],
                    load_object(str(question.response_json)),
                )
                if question.response_json
                else None
            ),
        ),
    )
