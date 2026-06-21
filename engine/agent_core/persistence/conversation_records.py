from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, selectinload

from engine.models import AgentArtifactRecord, AgentMessage, AgentRun, AgentRuntimeEventRecord, AgentSession


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


def serialize_runtime_event(row: AgentRuntimeEventRecord) -> dict[str, Any]:
    payload = _json(row.event_json, {})
    if not isinstance(payload, dict):
        payload = {}
    return {
        **payload,
        "event_id": payload.get("event_id") or row.id,
        "run_id": payload.get("run_id") or row.run_id,
        "conversation_id": payload.get("conversation_id") or row.session_id,
        "sequence": payload.get("sequence") or row.sequence,
        "created_at_ms": payload.get("created_at_ms") or row.created_at_ms,
        "type": payload.get("type") or row.type,
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
        "events": [
            serialize_runtime_event(event)
            for event in sorted(row.runtime_events, key=lambda item: item.sequence)
        ],
    }


def _depends_on_value(depends_on: Any) -> list[str]:
    if isinstance(depends_on, dict):
        depends_on = depends_on.get("depends_on", [])
    if not isinstance(depends_on, list):
        return []
    return [str(item) for item in depends_on if isinstance(item, str)]


def _depends_on(row: AgentArtifactRecord) -> list[str]:
    return _depends_on_value(_json(row.depends_on_json, []))


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
        "depends_on": _depends_on(row),
        "refs": _json(row.refs_json, {}),
        "created_at": _dt(row.created_at),
    }


def serialize_response_artifact(
    row: AgentRun,
    artifact: Any,
    sequence: int,
) -> dict[str, Any] | None:
    if not isinstance(artifact, dict):
        return None
    artifact_id = artifact.get("id")
    artifact_type = artifact.get("type")
    if not isinstance(artifact_id, str) or not isinstance(artifact_type, str):
        return None
    payload = artifact.get("payload")
    presentation = artifact.get("presentation")
    refs = artifact.get("refs")
    title = artifact.get("title")
    status = artifact.get("status")
    artifact_sequence = artifact.get("sequence")
    return {
        "id": artifact_id,
        "conversation_id": row.session_id,
        "run_id": row.id,
        "message_id": row.assistant_message_id,
        "semantic_id": artifact.get("semantic_id") if isinstance(artifact.get("semantic_id"), str) else None,
        "type": artifact_type,
        "title": title if isinstance(title, str) else artifact_type,
        "status": status if isinstance(status, str) else "completed",
        "sequence": artifact_sequence if isinstance(artifact_sequence, int) else sequence,
        "payload": payload if isinstance(payload, dict) else {},
        "presentation": presentation if isinstance(presentation, dict) else {},
        "depends_on": _depends_on_value(artifact.get("depends_on", [])),
        "refs": refs if isinstance(refs, dict) else {},
        "created_at": _dt(row.completed_at or row.updated_at),
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
            selectinload(AgentSession.runs).selectinload(AgentRun.runtime_events),
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
    serialized_artifacts = [serialize_artifact(artifact) for artifact in artifacts]
    artifact_ids = {artifact["id"] for artifact in serialized_artifacts}
    for run in runs:
        response = _json(run.response_json, {})
        response_artifacts = response.get("artifacts") if isinstance(response, dict) else None
        if not isinstance(response_artifacts, list):
            continue
        for index, artifact in enumerate(response_artifacts, start=1):
            serialized = serialize_response_artifact(run, artifact, index)
            if serialized is None or serialized["id"] in artifact_ids:
                continue
            artifact_ids.add(serialized["id"])
            serialized_artifacts.append(serialized)
    serialized_artifacts.sort(key=lambda item: (item.get("sequence") or 0, item.get("created_at") or ""))
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
        "artifacts": serialized_artifacts,
        "approvals": [],
    }
