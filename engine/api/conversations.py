from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.models import ChatConversation

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
    db.commit()
    return {"status": "ok"}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
    if row is not None:
        db.delete(row)
        db.commit()
    return {"status": "ok"}
