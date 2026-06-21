"""Session CRUD operations."""
from __future__ import annotations

import json
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
    session_id = req.conversation_id or _resolve_session_id(req)
    selected_tables = []
    if req.workspace_context is not None:
        selected_tables = req.workspace_context.selected_table_names
    existing = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if existing is None:
        existing = AgentSession(
            id=session_id,
            datasource_id=req.datasource_id,
            title=req.question[:80] if req.question else None,
            context_tables_json=json.dumps(selected_tables, ensure_ascii=False),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(existing)
        db.flush()
    else:
        existing.updated_at = datetime.now(UTC)  # type: ignore[assignment]
        if selected_tables:
            existing.context_tables_json = json.dumps(selected_tables, ensure_ascii=False)  # type: ignore[assignment]
        db.flush()
    return session_id
