"""Event and artifact recording, listing, and restore operations."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from engine.agent_core.types import AgentArtifact, AgentRuntimeEvent
from engine.models import (
    AgentArtifactRecord,
    AgentRun,
    AgentRuntimeEventRecord,
    AgentTraceEventRecord,
)
from engine.agent_core.persistence._common import (
    _safe_json,
    _safe_event_payload,
    _redact_trace_event,
    _artifact_to_dict,
    _parse_json,
)

logger = logging.getLogger("dbfox.agent.persistence")


def record_runtime_event(
    db: Session,
    session_id: str,
    event: AgentRuntimeEvent,
) -> None:
    try:
        record = AgentRuntimeEventRecord(
            id=event.event_id,
            run_id=event.run_id,
            session_id=session_id,
            sequence=event.sequence,
            type=event.type,
            event_json=_safe_json(_safe_event_payload(event)),
            created_at_ms=event.created_at_ms,
            created_at=datetime.now(UTC),
        )
        db.add(record)
        db.flush()
    except Exception as exc:
        logger.exception("Failed to record runtime event %s", event.event_id)
        raise exc


def record_artifact(
    db: Session,
    session_id: str,
    run_id: str,
    artifact: AgentArtifact,
    sequence: int | None = None,
) -> None:
    try:
        run = db.get(AgentRun, run_id)
        record = AgentArtifactRecord(
            id=artifact.id,
            run_id=run_id,
            session_id=session_id,
            message_id=run.assistant_message_id if run else None,
            semantic_id=artifact.semantic_id,
            type=artifact.type,
            title=artifact.title,
            produced_by_step=artifact.produced_by_step,
            depends_on_json=_safe_json(
                {"depends_on": artifact.depends_on} if artifact.depends_on else None
            ),
            payload_json=_safe_json(artifact.payload),
            presentation_json=artifact.presentation.model_dump_json(),
            refs_json=_safe_json(artifact.refs) if artifact.refs else None,
            status="completed",
            sequence=sequence,
            created_at=datetime.now(UTC),
        )
        db.add(record)
        db.flush()
    except Exception as exc:
        logger.exception("Failed to record artifact %s", artifact.id)
        raise exc


def get_latest_runtime_event_sequence(db: Session, run_id: str) -> int:
    latest = (
        db.query(func.max(AgentRuntimeEventRecord.sequence))
        .filter(AgentRuntimeEventRecord.run_id == run_id)
        .scalar()
        or 0
    )
    return int(latest)


def list_run_artifacts(db: Session, run_id: str) -> list[dict[str, Any]]:
    records = (
        db.query(AgentArtifactRecord)
        .filter(AgentArtifactRecord.run_id == run_id)
        .order_by(AgentArtifactRecord.sequence)
        .all()
    )
    return [_artifact_to_dict(r) for r in records]


def list_run_events(db: Session, run_id: str) -> list[dict[str, Any]]:
    records = (
        db.query(AgentRuntimeEventRecord)
        .filter(AgentRuntimeEventRecord.run_id == run_id)
        .order_by(AgentRuntimeEventRecord.sequence)
        .all()
    )
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "sequence": r.sequence,
            "type": r.type,
            "event": _parse_json(r.event_json) or {},
            "created_at_ms": r.created_at_ms,
        }
        for r in records
    ]


def list_run_trace_events(db: Session, run_id: str) -> list[dict[str, Any]]:
    records = (
        db.query(AgentTraceEventRecord)
        .filter(AgentTraceEventRecord.run_id == run_id)
        .order_by(AgentTraceEventRecord.sequence)
        .all()
    )
    return [
        _redact_trace_event(_parse_json(r.event_json) or {}, r)
        for r in records
    ]


def restore_artifact(db: Session, artifact_id: str) -> dict[str, Any] | None:
    record = db.query(AgentArtifactRecord).filter(AgentArtifactRecord.id == artifact_id).first()
    if record is None:
        return None
    d = _artifact_to_dict(record)
    d.pop("created_at", None)  # restore payload omits created_at
    return d


def restore_runtime_event(db: Session, event_id: str) -> dict[str, Any] | None:
    record = db.query(AgentRuntimeEventRecord).filter(AgentRuntimeEventRecord.id == event_id).first()
    if record is None:
        return None
    return {
        "id": record.id,
        "run_id": record.run_id,
        "sequence": record.sequence,
        "type": record.type,
        "event": _parse_json(record.event_json) or {},
        "created_at_ms": record.created_at_ms,
    }
