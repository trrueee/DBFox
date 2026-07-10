from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.agent import DBFoxAgentRuntime
from engine.agent.app.error_boundary import public_agent_failure, safe_agent_log
from engine.agent_core.persistence import get_conversation_detail, list_conversation_summaries
from engine.agent_core.types import AgentRunRequest, AgentWorkspaceContext
from engine.api.agent import _format_sse_event, attach_conversation_event_ids, sse_failed_event
from engine.db import get_db
from engine.errors import DBFoxError
from engine.models import AgentSession


router = APIRouter()
logger = logging.getLogger("dbfox.api.conversations")


class ConversationCreateRequest(BaseModel):
    datasource_id: str
    title: str | None = None
    context_tables: list[str] = Field(default_factory=list)


class ConversationPatchRequest(BaseModel):
    title: str | None = None
    context_tables: list[str] | None = None
    archived: bool | None = None


class ConversationMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    llm_credential_id: str | None = None
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


def _context_table_names_from_session(session: AgentSession) -> list[str]:
    try:
        raw = json.loads(session.context_tables_json or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


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

    context_table_names = _context_table_names_from_session(session)
    workspace_context = AgentWorkspaceContext(
        datasource_id=session.datasource_id,
        selected_table_names=context_table_names,
    )

    req = AgentRunRequest(
        datasource_id=session.datasource_id,
        question=payload.content,
        session_id=conversation_id,
        conversation_id=conversation_id,
        user_message_id=f"msg-user-{uuid4()}",
        assistant_message_id=f"msg-assistant-{uuid4()}",
        llm_credential_id=payload.llm_credential_id,
        api_base=payload.api_base,
        model_name=payload.model_name,
        workspace_context=workspace_context,
        execute=payload.execute,
    )

    def stream_events() -> Any:
        try:
            for event in DBFoxAgentRuntime(db).run_iter(req):
                attach_conversation_event_ids(event, req)
                yield _format_sse_event(event)
        except Exception as exc:
            db.rollback()
            failure = public_agent_failure(exc, operation="run")
            safe_agent_log(logger, operation="run", exc=exc)
            yield sse_failed_event(
                "conversation_stream_error",
                "",
                failure,
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
