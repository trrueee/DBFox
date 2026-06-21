from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.agent import DBFoxAgentRuntime
from engine.agent_core.persistence import get_conversation_detail, list_conversation_summaries
from engine.agent_core.types import AgentRunRequest
from engine.api.agent import _format_sse_event, attach_conversation_event_ids, sse_failed_event
from engine.db import get_db
from engine.errors import DBFoxError
from engine.models import AgentSession


router = APIRouter()


class ConversationCreateRequest(BaseModel):
    datasource_id: str
    title: str | None = None
    context_tables: list[str] = Field(default_factory=list)


class ConversationPatchRequest(BaseModel):
    title: str | None = None
    context_tables: list[str] | None = None
    archived: bool | None = None


class ConversationMessageRequest(BaseModel):
    content: str
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    execute: bool = True


class ConversationMessageStartResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    run_id: str | None = None


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return list_conversation_summaries(db)


@router.post("/conversations")
def create_conversation(
    payload: ConversationCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
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
    detail = get_conversation_detail(db, row.id)
    assert detail is not None
    return detail


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    detail = get_conversation_detail(db, conversation_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."},
        )
    return detail


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationMessageStartResponse)
def prepare_conversation_message(
    conversation_id: str,
    payload: ConversationMessageRequest,
    db: Session = Depends(get_db),
) -> ConversationMessageStartResponse:
    row = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."},
        )
    if not payload.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_MESSAGE", "message": "Message content is required."},
        )
    return ConversationMessageStartResponse(
        conversation_id=conversation_id,
        user_message_id=f"msg-user-{uuid4()}",
        assistant_message_id=f"msg-assistant-{uuid4()}",
        run_id=None,
    )


@router.post("/conversations/{conversation_id}/messages/stream")
def stream_conversation_message(
    conversation_id: str,
    payload: ConversationMessageRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    session = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."},
        )
    if not payload.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_MESSAGE", "message": "Message content is required."},
        )

    req = AgentRunRequest(
        datasource_id=session.datasource_id,
        question=payload.content,
        session_id=conversation_id,
        conversation_id=conversation_id,
        user_message_id=f"msg-user-{uuid4()}",
        assistant_message_id=f"msg-assistant-{uuid4()}",
        api_key=payload.api_key,
        api_base=payload.api_base,
        model_name=payload.model_name,
        execute=payload.execute,
    )

    def stream_events() -> Any:
        try:
            for event in DBFoxAgentRuntime(db).run_iter(req):
                attach_conversation_event_ids(event, req)
                yield _format_sse_event(event)
        except Exception as exc:
            db.rollback()
            yield sse_failed_event(
                "conversation_stream_error",
                "",
                f"Agent runtime failed: {exc}",
                "AGENT_RUNTIME_ERROR",
            )

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
    detail = get_conversation_detail(db, conversation_id)
    assert detail is not None
    return detail


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
    if row is not None:
        db.delete(row)
        db.commit()
    return {"status": "ok"}
