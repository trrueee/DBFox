"""Session CRUD operations."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from engine.agent_core.types import AgentRunRequest
from engine.models import AgentSession


def _resolve_session_id(req: AgentRunRequest) -> str:
    if req.session_id:
        return req.session_id
    if req.follow_up_context and req.follow_up_context.session_id:
        return req.follow_up_context.session_id
    from uuid import uuid4
    return str(uuid4())


def create_or_get_session(
    db: Session,
    req: AgentRunRequest,
    run_id: str,
) -> str:
    session_id = _resolve_session_id(req)
    existing = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if existing is None:
        existing = AgentSession(
            id=session_id,
            datasource_id=req.datasource_id,
            title=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(existing)
        db.flush()
    else:
        existing.updated_at = datetime.now(UTC)  # type: ignore[assignment]
        db.flush()
    return session_id
