from __future__ import annotations

import json
import queue
import threading
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.approval import ApprovalConflict
from engine.agent.events import COMMIT_NOTIFICATIONS, LiveDelta, LiveStreamGap, RuntimeEvent
from engine.agent.loop import LIVE_STREAM_HUB
from engine.agent.question import QuestionAnswer, QuestionConflict, QuestionStatus
from engine.agent.projection import conversation_snapshot
from engine.agent.repositories.approval import ApprovalRepository
from engine.agent.repositories.question import QuestionRepository
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import EventHistoryGap, SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.session import DeliveryMode
from engine.db import SessionLocal, get_db
from engine.errors import DBFoxError
from engine.llm.config import LlmConfigurationError, normalize_product_llm_preferences
from engine.models import AgentSession, DataSource


router = APIRouter()


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


@router.get("/conversations")
def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    rows = db.execute(
        select(AgentSession).order_by(AgentSession.updated_at.desc()).offset(offset).limit(limit)
    ).scalars().all()
    return [{
        "id": str(row.id), "datasource_id": str(row.datasource_id), "title": str(row.title),
        "selected_artifact_id": str(row.selected_artifact_id) if row.selected_artifact_id else None,
        "updated_at": row.updated_at.isoformat(),
    } for row in rows]


@router.post("/conversations")
def create_conversation(
    payload: ConversationCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    begin_agent_write(db)
    if db.get(DataSource, payload.datasource_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "DATASOURCE_NOT_FOUND", "message": "Datasource not found."},
        )
    now = datetime.now(UTC)
    row = AgentSession(
        datasource_id=payload.datasource_id,
        title=payload.title or "New conversation",
        context_tables_json=json.dumps(payload.context_tables, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    detail = conversation_snapshot(db, str(row.id))
    assert detail is not None
    return detail


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    detail = conversation_snapshot(db, conversation_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."},
        )
    return detail


@router.patch("/conversations/{conversation_id}")
def patch_conversation(
    conversation_id: str,
    payload: ConversationPatchRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    row = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
    if row is None:
        raise DBFoxError("Conversation not found.", code="CONVERSATION_NOT_FOUND")
    if payload.title is not None:
        row.title = payload.title
    if payload.context_tables is not None:
        row.context_tables_json = json.dumps(payload.context_tables, ensure_ascii=False)
    if payload.archived is not None:
        row.archived_at = datetime.now(UTC) if payload.archived else None
    row.updated_at = datetime.now(UTC)
    db.commit()
    detail = conversation_snapshot(db, conversation_id)
    assert detail is not None
    return detail


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
    if row is not None:
        db.delete(row)
        db.commit()
    return {"status": "ok"}


def _coordinator(request: Request):
    value = getattr(request.app.state, "agent_coordinator", None)
    if value is None or not bool(getattr(value, "available", False)):
        raise HTTPException(
            status_code=503,
            detail={"code": "AGENT_UNAVAILABLE", "message": "智能分析暂时不可用，请稍后重试。"},
        )
    return value


@router.post("/conversations/{conversation_id}/inputs", status_code=202)
def admit_conversation_input(
    conversation_id: str,
    payload: ConversationInputRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    coordinator = _coordinator(request)
    aggregate = db.get(AgentSession, conversation_id)
    if aggregate is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."},
        )
    datasource = db.get(DataSource, aggregate.datasource_id)
    if datasource is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "DATASOURCE_NOT_FOUND", "message": "Datasource not found."},
        )
    try:
        preferences = normalize_product_llm_preferences(
            llm_credential_id=payload.llm_credential_id,
            api_base=payload.api_base,
            model_name=payload.model_name,
        )
        admission = SessionRepository(db).admit(
            session_id=conversation_id,
            datasource_id=str(datasource.id),
            datasource_generation=int(datasource.connection_generation),
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
    except (ValueError, LlmConfigurationError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={"code": getattr(exc, "code", "AGENT_INPUT_INVALID"), "message": "输入或模型配置无效。"},
        ) from None
    coordinator.wake(conversation_id)
    return {
        "session_id": conversation_id,
        "input_id": admission.input_id,
        "run_id": admission.run_id,
        "user_message_id": admission.user_message_id,
        "assistant_message_id": admission.assistant_message_id,
        "input_sequence": admission.input_sequence,
        "event_cursor": int(db.get(AgentSession, conversation_id).event_sequence),
        "stream_path": f"/conversations/{conversation_id}/stream",
    }


@router.get("/conversations/{conversation_id}/events")
def list_conversation_events(
    conversation_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1_000),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    if db.get(AgentSession, conversation_id) is None:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND"})
    try:
        events = SessionRepository(db).list_events(
            conversation_id, after_sequence=after_sequence, limit=limit
        )
    except EventHistoryGap as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONVERSATION_SNAPSHOT_REQUIRED",
                "floor_sequence": exc.floor_sequence,
                "current_sequence": exc.current_sequence,
            },
        ) from exc
    return [item.model_dump(mode="json") for item in events]


@router.get("/conversations/{conversation_id}/stream")
def stream_conversation(
    conversation_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
) -> StreamingResponse:
    with SessionLocal() as db:
        if db.get(AgentSession, conversation_id) is None:
            raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND"})
    last_event_id = request.headers.get("last-event-id", "").strip()
    if last_event_id.isdigit():
        after_sequence = max(after_sequence, int(last_event_id))
    with SessionLocal() as db:
        try:
            SessionRepository(db).list_events(
                conversation_id, after_sequence=after_sequence, limit=1
            )
        except EventHistoryGap as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONVERSATION_SNAPSHOT_REQUIRED",
                    "floor_sequence": exc.floor_sequence,
                    "current_sequence": exc.current_sequence,
                },
            ) from exc
    return StreamingResponse(
        _conversation_stream(conversation_id, after_sequence),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations/{conversation_id}/artifact-selection")
def select_conversation_artifact(
    conversation_id: str,
    payload: ArtifactSelectionRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        SessionRepository(db).select_artifact(
            session_id=conversation_id, artifact_id=payload.artifact_id, selected_by="user"
        )
        db.commit()
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=404, detail={"code": "ARTIFACT_NOT_FOUND"}) from None
    return {"session_id": conversation_id, "artifact_id": payload.artifact_id}


@router.post("/approvals/{approval_id}/resolve")
def resolve_approval(
    approval_id: str,
    payload: ApprovalResolutionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    coordinator = _coordinator(request)
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
    coordinator.wake(value.session_id)
    return value.model_dump(mode="json")


@router.post("/questions/{question_id}/resolve")
def resolve_question(
    question_id: str,
    payload: QuestionResolutionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    coordinator = _coordinator(request)
    try:
        answer = QuestionAnswer(
            selected_value=payload.selected_value,
            text=payload.text,
        )
        value = QuestionRepository(db).resolve(
            question_id=question_id,
            expected_version=payload.expected_version,
            answer=answer,
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
        coordinator.wake(value.session_id)
    return value.model_dump(mode="json")


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    coordinator = _coordinator(request)
    try:
        run = RunRepository(db).request_cancel(run_id=run_id)
        execution_id = str(run.execution_id or "")
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"}) from None
    if execution_id:
        from engine.query_registry import QUERY_REGISTRY
        QUERY_REGISTRY.cancel(execution_id)
    coordinator.wake(str(run.session_id))
    return {"run_id": str(run.id), "status": str(run.status), "version": int(run.version)}


def _conversation_stream(session_id: str, after_sequence: int):
    commit_subscription = COMMIT_NOTIFICATIONS.subscribe(session_id)
    live_subscription = LIVE_STREAM_HUB.subscribe_session(session_id)
    signals: queue.Queue[tuple[str, object]] = queue.Queue()
    stopped = threading.Event()

    def forward_commits() -> None:
        while not stopped.is_set():
            value = commit_subscription.receive(timeout=1.0)
            if value is not None:
                signals.put(("commit", value))

    def forward_live() -> None:
        while not stopped.is_set():
            try:
                value = live_subscription.receive(timeout=1.0)
            except LiveStreamGap:
                # End this response cleanly. The client reloads the durable
                # snapshot and reconnects from its authoritative cursor.
                signals.put(("gap", None))
                return
            if value is not None:
                signals.put(("live", value))

    threads = [
        threading.Thread(target=forward_commits, daemon=True),
        threading.Thread(target=forward_live, daemon=True),
    ]
    for thread in threads:
        thread.start()
    cursor = after_sequence
    try:
        while True:
            try:
                with SessionLocal() as db:
                    events = SessionRepository(db).list_events(session_id, after_sequence=cursor, limit=500)
            except EventHistoryGap:
                return
            for event in events:
                cursor = event.sequence
                yield _sse_event(event.event_type.value, event.model_dump(mode="json"), event_id=str(cursor))
            try:
                kind, value = signals.get(timeout=15.0)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if kind == "live":
                delta = value
                assert isinstance(delta, LiveDelta)
                yield _sse_event("live.delta", delta.model_dump(mode="json"))
            elif kind == "gap":
                return
            # commit notifications deliberately carry no payload; loop replays SQL truth.
    finally:
        stopped.set()
        commit_subscription.close()
        live_subscription.close()


def _sse_event(event_type: str, payload: object, event_id: str | None = None) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    identity = f"id: {event_id}\n" if event_id else ""
    return f"{identity}event: {event_type}\ndata: {encoded}\n\n"
