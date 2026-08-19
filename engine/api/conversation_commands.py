from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from engine.agent.approval import Approval, ApprovalConflict
from engine.agent.projection import conversation_snapshot
from engine.agent.question import (
    QuestionAnswer,
    QuestionConflict,
    QuestionRequest,
    QuestionStatus,
)
from engine.agent.repositories.approval import ApprovalRepository
from engine.agent.repositories.question import QuestionRepository
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.run_item import project_run
from engine.app.safe_errors import FixedErrorCode, fixed_error_detail
from engine.api.conversation_common import coordinator
from engine.api.conversation_contracts import (
    ApprovalResolutionRequest,
    ArtifactSelectionRequest,
    ConversationCreateRequest,
    ConversationInputRequest,
    ConversationPatchRequest,
    QuestionResolutionRequest,
)
from engine.db import get_db
from engine.errors import DBFoxError
from engine.json_codec import loads as json_loads
from engine.llm.config import LlmConfigurationError, normalize_product_llm_preferences
from engine.models import AgentRun, AgentRunItemRecord, AgentSession, DataSource, Project
from engine.runtime_composition import authorize_project_resources
from engine.schemas.api_responses import (
    ArtifactSelectionResponse,
    ConversationDeleteResponse,
    ConversationInputAcceptedResponse,
    ConversationSnapshotResponse,
    RunCancelledResponse,
)


router = APIRouter()


@router.post("/conversations", response_model=ConversationSnapshotResponse)
def create_conversation(
    payload: ConversationCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    project = db.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found."},
        )
    datasource_id: str | None = None
    if payload.datasource_id is not None:
        datasource = db.get(DataSource, payload.datasource_id)
        if datasource is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "DATASOURCE_NOT_FOUND", "message": "Datasource not found."},
            )
        if str(datasource.project_id) != payload.project_id:
            raise HTTPException(
                status_code=400,
                detail={"code": "DATASOURCE_PROJECT_MISMATCH", "message": "Datasource does not belong to the specified Project."},
            )
        datasource_id = str(datasource.id)
    row = SessionRepository(db).create(
        project_id=payload.project_id,
        datasource_id=datasource_id,
        title=payload.title or "New conversation",
        context_tables=payload.context_tables,
    )
    db.commit()
    detail = conversation_snapshot(db, str(row.id))
    if detail is None:
        raise RuntimeError("Committed conversation projection is missing")
    return detail


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationSnapshotResponse,
)
def patch_conversation(
    conversation_id: str,
    payload: ConversationPatchRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    row = SessionRepository(db).update_metadata(
        session_id=conversation_id,
        title=payload.title,
        context_tables=payload.context_tables,
        archived=payload.archived,
    )
    if row is None:
        raise DBFoxError("Conversation not found.", code="CONVERSATION_NOT_FOUND")
    db.commit()
    detail = conversation_snapshot(db, conversation_id)
    if detail is None:
        raise RuntimeError("Committed conversation projection is missing")
    return detail


@router.delete(
    "/conversations/{conversation_id}",
    response_model=ConversationDeleteResponse,
)
def delete_conversation(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    deletion = SessionRepository(db).request_delete(session_id=conversation_id)
    active_coordinator = coordinator(request) if deletion.status == "deleting" else None
    db.commit()
    if deletion.execution_ids:
        from engine.query_registry import QUERY_REGISTRY

        for execution_id in deletion.execution_ids:
            QUERY_REGISTRY.cancel(execution_id)
    if active_coordinator is not None:
        active_coordinator.wake(conversation_id)
    return {"status": deletion.status}


@router.post(
    "/conversations/{conversation_id}/inputs",
    response_model=ConversationInputAcceptedResponse,
    status_code=202,
)
def admit_conversation_input(
    conversation_id: str,
    payload: ConversationInputRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    active_coordinator = coordinator(request)
    aggregate = db.get(AgentSession, conversation_id)
    if aggregate is None or aggregate.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."},
        )

    try:
        resource_refs = authorize_project_resources(
            db,
            project_id=str(aggregate.project_id or ""),
            requested=payload.requested_resources,
            fallback_datasource_id=str(aggregate.datasource_id) if aggregate.datasource_id else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_RESOURCE_REQUEST", "message": str(exc)},
        ) from exc

    try:
        preferences = normalize_product_llm_preferences(
            llm_credential_id=payload.llm_credential_id,
            api_base=payload.api_base,
            model_name=payload.model_name,
        )
        admission = SessionRepository(db).admit(
            session_id=conversation_id,
            resource_refs=tuple(resource_refs),
            content=payload.content,
            idempotency_key=payload.idempotency_key,
            llm_credential_id=payload.llm_credential_id,
            api_base=preferences.api_base,
            model_name=preferences.model_name,
            request_payload={
                "content": payload.content,
                "delivery_mode": payload.delivery_mode.value,
            },
            delivery_mode=payload.delivery_mode,
            selected_artifact_ids=payload.selected_artifact_ids,
            workspace_context=payload.workspace_context,
        )
        db.commit()
        run = db.get(AgentRun, admission.run_id)
        user_item = db.get(AgentRunItemRecord, admission.user_message_id)
        aggregate = db.get(AgentSession, conversation_id)
        if run is None or user_item is None or aggregate is None:
            raise RuntimeError("Committed Agent admission projection is incomplete")
        admission_projection = {
            "protocol_version": 2,
            "cursor": int(aggregate.event_sequence or 0),
            "items": [json_loads(str(user_item.item_json))],
            "runs": [project_run(run)],
        }
    except LlmConfigurationError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=fixed_error_detail(exc.code),
        ) from None
    except ValueError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=fixed_error_detail(FixedErrorCode.AGENT_INPUT_INVALID),
        ) from None
    active_coordinator.wake(conversation_id)
    return {
        "session_id": conversation_id,
        "input_id": admission.input_id,
        "run_id": admission.run_id,
        "user_message_id": admission.user_message_id,
        "input_sequence": admission.input_sequence,
        "event_cursor": admission_projection["cursor"],
        "projection": admission_projection,
        "stream_path": f"/conversations/{conversation_id}/stream",
    }


@router.post(
    "/conversations/{conversation_id}/artifact-selection",
    response_model=ArtifactSelectionResponse,
)
def select_conversation_artifact(
    conversation_id: str,
    payload: ArtifactSelectionRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        SessionRepository(db).select_artifact(
            session_id=conversation_id,
            artifact_id=payload.artifact_id,
            selected_by="user",
        )
        db.commit()
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=404, detail={"code": "ARTIFACT_NOT_FOUND"}) from None
    return {"session_id": conversation_id, "artifact_id": payload.artifact_id}


@router.post("/approvals/{approval_id}/resolve", response_model=Approval)
def resolve_approval(
    approval_id: str,
    payload: ApprovalResolutionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    active_coordinator = coordinator(request)
    try:
        value = ApprovalRepository(db).resolve(
            approval_id=approval_id,
            expected_version=payload.expected_version,
            approved=payload.decision == "approve",
            actor="user",
            note=payload.note,
        )
        db.commit()
    except ApprovalConflict:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "APPROVAL_CONFLICT", "message": "批准状态已变化，请刷新后重试。"},
        ) from None
    active_coordinator.wake(value.session_id)
    return value.model_dump(mode="json")


@router.post("/questions/{question_id}/resolve", response_model=QuestionRequest)
def resolve_question(
    question_id: str,
    payload: QuestionResolutionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    active_coordinator = coordinator(request)
    try:
        value = QuestionRepository(db).resolve(
            question_id=question_id,
            expected_version=payload.expected_version,
            answer=QuestionAnswer(
                selected_value=payload.selected_value,
                text=payload.text,
            ),
            actor="user",
        )
        db.commit()
    except (QuestionConflict, ValueError):
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "QUESTION_CONFLICT", "message": "问题状态已变化，请刷新后重试。"},
        ) from None
    if value.status is QuestionStatus.ANSWERED:
        active_coordinator.wake(value.session_id)
    return value.model_dump(mode="json")


@router.post("/runs/{run_id}/cancel", response_model=RunCancelledResponse)
def cancel_run(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    active_coordinator = coordinator(request)
    try:
        run = RunRepository(db).request_cancel(run_id=run_id)
        execution_id = str(run.execution_id or "")
        running_invocations = ToolInvocationRepository(db).running_invocation_ids_for_run(
            run_id=run_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"}) from None
    if execution_id:
        from engine.query_registry import QUERY_REGISTRY

        QUERY_REGISTRY.cancel(execution_id)
    from engine.query_registry import QUERY_REGISTRY

    for invocation_id in running_invocations:
        QUERY_REGISTRY.cancel(invocation_id)
    active_coordinator.wake(str(run.session_id))
    return {"run_id": str(run.id), "status": str(run.status), "version": int(run.version or 0)}
