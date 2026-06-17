from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.models import ChatConversation, AgentSession
from engine.agent_core.persistence import sync_chat_conversation_from_session

logger = logging.getLogger("dbfox.api.conversations")
router = APIRouter()


class ConversationRecordPayload(BaseModel):
    id: str
    title: str
    created_at: int
    updated_at: int
    context_tables_json: str = "[]"
    messages_json: str = "[]"
    artifacts_json: str = "[]"


@router.get("/conversations", response_model=list[ConversationRecordPayload])
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationRecordPayload]:
    # Self-healing: ensure all AgentSessions have a ChatConversation row.
    # Use a single outerjoin query to avoid N+1 per-session lookups.
    try:
        missing_sessions = (
            db.query(AgentSession)
            .outerjoin(ChatConversation, AgentSession.id == ChatConversation.id)
            .filter(ChatConversation.id == None)
            .all()
        )
        failed_count = 0
        for s in missing_sessions:
            try:
                sync_chat_conversation_from_session(db, s.id)
            except Exception:
                failed_count += 1
                logger.exception("Failed to sync legacy/missing session %s to ChatConversation", s.id)
        if failed_count > 0:
            logger.warning("Self-healing: %d/%d sessions could not be synced", failed_count, len(missing_sessions))
    except Exception:
        logger.exception("Failed to query AgentSessions for self-healing sync")

    rows = (
        db.query(ChatConversation)
        .order_by(ChatConversation.updated_at.desc())
        .all()
    )
    return [
        ConversationRecordPayload(
            id=row.id,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
            context_tables_json=row.context_tables_json,
            messages_json=row.messages_json,
            artifacts_json=row.artifacts_json,
        )
        for row in rows
    ]


@router.put("/conversations/{conversation_id}")
def save_conversation(
    conversation_id: str,
    payload: ConversationRecordPayload,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if payload.id != conversation_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "CONVERSATION_ID_MISMATCH", "message": "Conversation id mismatch."},
        )

    try:
        row = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
        if row is None:
            row = ChatConversation(id=conversation_id)
            db.add(row)

        row.title = payload.title
        row.created_at = payload.created_at
        row.updated_at = payload.updated_at
        row.context_tables_json = payload.context_tables_json
        row.messages_json = payload.messages_json
        row.artifacts_json = payload.artifacts_json

        session = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
        if session is not None:
            session.title = payload.title

        db.commit()
        return {"status": "ok"}
    except Exception:
        db.rollback()
        raise


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        session = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
        if session is not None:
            db.delete(session)

        row = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
        if row is not None:
            db.delete(row)
            
        db.commit()
        return {"status": "ok"}
    except Exception:
        db.rollback()
        raise
