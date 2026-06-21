from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.db import get_db

router = APIRouter()


class ConversationRecordPayload(BaseModel):
    id: str
    title: str
    created_at: int
    updated_at: int
    context_tables_json: str = "[]"
    messages_json: str = "[]"
    artifacts_json: str = "[]"


def heal_missing_conversations(db: Session) -> None:
    """Temporary no-op until the structured conversation API replaces this module."""
    del db


@router.get("/conversations", response_model=list[ConversationRecordPayload])
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationRecordPayload]:
    del db
    return []


@router.put("/conversations/{conversation_id}")
def save_conversation(
    conversation_id: str,
    payload: ConversationRecordPayload,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    del conversation_id, payload, db
    raise HTTPException(
        status_code=404,
        detail={
            "code": "CONVERSATION_API_REDESIGN_PENDING",
            "message": "Legacy conversations API is unavailable during the structured conversation redesign.",
        },
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    del conversation_id, db
    raise HTTPException(
        status_code=404,
        detail={
            "code": "CONVERSATION_API_REDESIGN_PENDING",
            "message": "Legacy conversations API is unavailable during the structured conversation redesign.",
        },
    )
