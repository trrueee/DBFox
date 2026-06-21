from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, selectinload

from engine.models import AgentArtifactRecord, AgentMessage, AgentRun, AgentSession


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _json(text: str | None, fallback: Any) -> Any:
    if not text:
        return fallback
    try:
        return json.loads(text)
    except Exception:
        return fallback


def serialize_message(row: AgentMessage) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.session_id,
        "role": row.role,
        "content": row.content,
        "status": row.status,
        "sequence": row.sequence,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


def serialize_run(row: AgentRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.session_id,
        "parent_run_id": row.parent_run_id,
        "user_message_id": row.user_message_id,
        "assistant_message_id": row.assistant_message_id,
        "datasource_id": row.datasource_id,
        "question": row.question,
        "status": row.status,
        "error_code": row.error_code,
        "error_message": row.error_message or row.error,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
        "started_at": _dt(row.started_at),
        "completed_at": _dt(row.completed_at),
    }


def serialize_artifact(row: AgentArtifactRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.session_id,
        "run_id": row.run_id,
        "message_id": row.message_id,
        "semantic_id": row.semantic_id,
        "type": row.type,
        "title": row.title,
        "status": row.status,
        "sequence": row.sequence,
        "payload": _json(row.payload_json, {}),
        "presentation": _json(row.presentation_json, {}),
        "depends_on": _json(row.depends_on_json, []),
        "refs": _json(row.refs_json, {}),
        "created_at": _dt(row.created_at),
    }


def list_conversation_summaries(db: Session) -> list[dict[str, Any]]:
    sessions = (
        db.query(AgentSession)
        .options(
            selectinload(AgentSession.messages),
            selectinload(AgentSession.runs).selectinload(AgentRun.artifacts),
        )
        .filter(AgentSession.deleted_at.is_(None))
        .order_by(AgentSession.updated_at.desc())
        .all()
    )

    summaries: list[dict[str, Any]] = []
    for session in sessions:
        messages = sorted(session.messages, key=lambda item: item.sequence)
        runs = sorted(session.runs, key=lambda item: item.created_at)
        last_message = messages[-1].content if messages else ""
        summaries.append(
            {
                "id": session.id,
                "title": session.title or (messages[0].content[:80] if messages else "New conversation"),
                "datasource_id": session.datasource_id,
                "updated_at": _dt(session.updated_at),
                "last_message": last_message,
                "message_count": len(messages),
                "run_status": runs[-1].status if runs else None,
                "artifact_count": sum(len(run.artifacts) for run in runs),
            }
        )
    return summaries


def get_conversation_detail(db: Session, conversation_id: str) -> dict[str, Any] | None:
    session = (
        db.query(AgentSession)
        .options(
            selectinload(AgentSession.messages),
            selectinload(AgentSession.runs).selectinload(AgentRun.artifacts),
            selectinload(AgentSession.runs).selectinload(AgentRun.approvals),
            selectinload(AgentSession.runs).selectinload(AgentRun.trace_events),
        )
        .filter(AgentSession.id == conversation_id, AgentSession.deleted_at.is_(None))
        .first()
    )
    if session is None:
        return None

    runs = sorted(session.runs, key=lambda item: item.created_at)
    artifacts = sorted(
        [artifact for run in runs for artifact in run.artifacts],
        key=lambda item: (item.sequence or 0, item.created_at),
    )
    return {
        "id": session.id,
        "title": session.title or "",
        "datasource_id": session.datasource_id,
        "context_tables": _json(session.context_tables_json, []),
        "created_at": _dt(session.created_at),
        "updated_at": _dt(session.updated_at),
        "messages": [
            serialize_message(message)
            for message in sorted(session.messages, key=lambda item: item.sequence)
        ],
        "runs": [serialize_run(run) for run in runs],
        "artifacts": [serialize_artifact(artifact) for artifact in artifacts],
        "approvals": [],
    }
