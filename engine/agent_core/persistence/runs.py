"""Run lifecycle operations — start, complete, fail, cancel, query."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from engine.errors import DBFoxError
from engine.agent_core.types import AgentRunRequest, AgentRunResponse
from engine.models import AgentRun, AgentArtifactRecord, ChatConversation
from engine.agent_core.persistence._common import (
    _safe_json,
    _restore_response,
    _redact_response,
    _load_run_artifacts,
    _parse_json,
    _redact_trace_for_storage,
    _summarize_artifact_payload,
)

logger = logging.getLogger("dbfox.agent.persistence")


def start_run(
    db: Session,
    req: AgentRunRequest,
    run_id: str,
    session_id: str,
) -> None:
    run = AgentRun(
        id=run_id,
        session_id=session_id,
        parent_run_id=req.parent_run_id or (
            req.follow_up_context.parent_run_id if req.follow_up_context else None
        ),
        datasource_id=req.datasource_id,
        question=req.question,
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(run)
    db.flush()

    if req.workspace_context and req.workspace_context.selected_table_names:
        row = db.query(ChatConversation).filter(ChatConversation.id == session_id).first()
        if row is None:
            row = ChatConversation(
                id=session_id,
                title=req.question,
                created_at=int(datetime.now(UTC).timestamp() * 1000),
                updated_at=int(datetime.now(UTC).timestamp() * 1000),
            )
            db.add(row)
        row.context_tables_json = json.dumps(req.workspace_context.selected_table_names)
        db.flush()

    from engine.agent_core.persistence.conversations import sync_chat_conversation_from_session
    sync_chat_conversation_from_session(db, session_id)


def complete_run(db: Session, response: AgentRunResponse) -> None:
    try:
        run = db.query(AgentRun).filter(AgentRun.id == response.run_id).first()
        if run is None:
            logger.warning("Cannot complete run %s: run not found", response.run_id)
            return
        run.status = "success" if response.success else "failed"  # type: ignore[assignment]
        run.current_step_name = None  # type: ignore[assignment]
        run.waiting_approval_id = None  # type: ignore[assignment]
        run.response_json = _safe_json(_redact_response(response))  # type: ignore[assignment]
        run.context_summary = response.context_summary  # type: ignore[assignment]
        run.error = response.error  # type: ignore[assignment]
        run.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        run.updated_at = datetime.now(UTC)  # type: ignore[assignment]
        db.flush()
        _save_trace_events(db, response)
        from engine.agent_core.persistence.conversations import sync_chat_conversation_from_session
        sync_chat_conversation_from_session(db, run.session_id)
    except Exception as exc:
        logger.exception("Failed to complete run %s", response.run_id)
        raise exc


def _save_trace_events(db: Session, response: AgentRunResponse) -> None:
    if not response.trace_events:
        return
    from engine.models import AgentTraceEventRecord
    for idx, trace in enumerate(response.trace_events):
        try:
            record = AgentTraceEventRecord(
                id=f"trace_{response.run_id[:8]}_{idx}_{trace.sequence or idx}",
                run_id=response.run_id,
                session_id=response.session_id,
                sequence=trace.sequence or idx + 1,
                type=trace.type,
                event_json=_safe_json(
                    _redact_trace_for_storage(trace.model_dump())
                ),
                created_at_ms=0,
                created_at=datetime.now(UTC),
            )
            db.add(record)
        except Exception:
            logger.warning("Failed to save trace event %s", trace.event_id)
    db.flush()


def fail_run(
    db: Session,
    run_id: str,
    session_id: str,
    error: str,
    response: AgentRunResponse | None = None,
) -> None:
    try:
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run is None:
            logger.warning("Cannot fail run %s: run not found", run_id)
            return
        run.status = "failed"  # type: ignore[assignment]
        run.current_step_name = None  # type: ignore[assignment]
        run.waiting_approval_id = None  # type: ignore[assignment]
        run.error = error  # type: ignore[assignment]
        if response is not None:
            run.response_json = _safe_json(_redact_response(response))  # type: ignore[assignment]
            run.context_summary = response.context_summary  # type: ignore[assignment]
        run.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        run.updated_at = datetime.now(UTC)  # type: ignore[assignment]
        db.flush()
        from engine.agent_core.persistence.conversations import sync_chat_conversation_from_session
        sync_chat_conversation_from_session(db, session_id)
    except Exception:
        logger.exception("Failed to record failure for run %s", run_id)


def cancel_run(db: Session, *, run_id: str) -> None:
    """Mark an agent run as cancelled by user request."""
    try:
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run is None:
            logger.warning("Cannot cancel run %s: run not found", run_id)
            return
        run.status = "cancelled"  # type: ignore[assignment]
        run.current_step_name = None  # type: ignore[assignment]
        run.waiting_approval_id = None  # type: ignore[assignment]
        run.error = "User cancelled the agent run."  # type: ignore[assignment]
        run.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        run.updated_at = datetime.now(UTC)  # type: ignore[assignment]
        db.flush()
        from engine.agent_core.persistence.conversations import sync_chat_conversation_from_session
        sync_chat_conversation_from_session(db, run.session_id)
    except Exception:
        logger.exception("Failed to cancel run %s", run_id)


def mark_run_waiting_approval(
    db: Session,
    *,
    run_id: str,
    approval_id: str,
    current_step_name: str,
    response: AgentRunResponse | None = None,
) -> None:
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run is None:
        raise DBFoxError("Agent run not found.", code="RUN_NOT_FOUND")
    run.status = "waiting_approval"  # type: ignore[assignment]
    run.current_step_name = current_step_name  # type: ignore[assignment]
    run.waiting_approval_id = approval_id  # type: ignore[assignment]
    run.error = None  # type: ignore[assignment]
    run.completed_at = None  # type: ignore[assignment]
    run.updated_at = datetime.now(UTC)  # type: ignore[assignment]
    if response is not None:
        run.response_json = _safe_json(_redact_response(response))  # type: ignore[assignment]
        run.context_summary = response.context_summary  # type: ignore[assignment]
    db.flush()
    from engine.agent_core.persistence.conversations import sync_chat_conversation_from_session
    sync_chat_conversation_from_session(db, run.session_id)


def mark_run_resumed(db: Session, *, run_id: str, current_step_name: str | None = "query_database") -> None:
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run is None:
        raise DBFoxError("Agent run not found.", code="RUN_NOT_FOUND")
    run.status = "running"  # type: ignore[assignment]
    run.current_step_name = current_step_name  # type: ignore[assignment]
    run.waiting_approval_id = None  # type: ignore[assignment]
    run.error = None  # type: ignore[assignment]
    run.completed_at = None  # type: ignore[assignment]
    run.updated_at = datetime.now(UTC)  # type: ignore[assignment]
    db.flush()
    from engine.agent_core.persistence.conversations import sync_chat_conversation_from_session
    sync_chat_conversation_from_session(db, run.session_id)


def get_run(db: Session, run_id: str) -> AgentRunResponse | None:
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run is None or run.response_json is None:
        return None
    return _restore_response(run)


def list_session_runs(db: Session, session_id: str) -> list[dict[str, Any]]:
    from engine.models import AgentArtifactRecord
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.session_id == session_id)
        .order_by(AgentRun.created_at.desc())
        .all()
    )
    result = []
    for r in runs:
        artifact_count = (
            db.query(AgentArtifactRecord)
            .filter(AgentArtifactRecord.run_id == r.id)
            .count()
        )
        result.append({
            "run_id": r.id,
            "session_id": r.session_id,
            "parent_run_id": r.parent_run_id,
            "question": r.question,
            "status": r.status,
            "error": r.error,
            "artifact_count": artifact_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        })
    return result


def get_recent_run(db: Session, datasource_id: str) -> AgentRunResponse | None:
    run = (
        db.query(AgentRun)
        .filter(
            AgentRun.datasource_id == datasource_id,
            AgentRun.response_json.isnot(None),
        )
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    if run is None:
        return None
    return _restore_response(run)


def get_run_sequence_by_session(db: Session, session_id: str) -> list[AgentRun]:
    """Retrieves all agent runs associated with a session, sorted chronologically."""
    return (
        db.query(AgentRun)
        .filter(AgentRun.session_id == session_id)
        .order_by(AgentRun.created_at.asc())
        .all()
    )


def build_followup_context_from_run(
    db: Session,
    parent_run_id: str,
) -> Any:
    from engine.agent_core.types import AgentFollowUpContext, AgentContextArtifact
    run = db.query(AgentRun).filter(AgentRun.id == parent_run_id).first()
    if run is None:
        return None

    artifacts = _load_run_artifacts(db, parent_run_id)

    response_data = _parse_json(run.response_json) if run.response_json else None
    previous_answer = None
    if response_data:
        answer = response_data.get("answer")
        if isinstance(answer, dict):
            previous_answer = answer.get("answer")
        if not previous_answer:
            previous_answer = response_data.get("explanation")

    return AgentFollowUpContext(
        session_id=run.session_id,
        parent_run_id=run.id,
        previous_question=run.question,
        previous_answer=previous_answer,
        artifacts=[
            AgentContextArtifact(
                id=artifact.id,
                type=artifact.type,
                title=artifact.title,
                summary=_summarize_artifact_payload(
                    _parse_json(artifact.payload_json) or {}
                ),
                payload=_parse_json(artifact.payload_json) or {},
            )
            for artifact in artifacts[:8]
        ],
    )
