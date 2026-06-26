"""Checkpoint CRUD operations."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from engine.agent_core.types import AgentCheckpointRecord
from engine.models import AgentCheckpoint
from engine.agent_core.persistence._common import (
    _safe_json,
    _safe_checkpoint_payload,
    _checkpoint_record,
    _parse_json_any,
)


def _latest_checkpoint_model(db: Session, run_id: str) -> AgentCheckpoint | None:
    return (
        db.query(AgentCheckpoint)
        .filter(AgentCheckpoint.run_id == run_id)
        .order_by(AgentCheckpoint.checkpoint_index.desc(), AgentCheckpoint.created_at.desc())
        .first()
    )


def save_checkpoint(
    db: Session,
    *,
    run_id: str,
    session_id: str,
    status: str,
    current_step_name: str | None,
    next_step_name: str | None,
    plan: Any | None,
    state: dict[str, Any],
    completed_steps: list[dict[str, Any]],
    pending_steps: list[dict[str, Any]],
    artifacts: list[dict[str, Any]] | None = None,
) -> AgentCheckpointRecord:
    latest_index = (
        db.query(func.max(AgentCheckpoint.checkpoint_index))
        .filter(AgentCheckpoint.run_id == run_id)
        .scalar()
        or 0
    )
    checkpoint = AgentCheckpoint(
        id=f"checkpoint_{uuid.uuid4().hex}",
        run_id=run_id,
        session_id=session_id,
        checkpoint_index=int(latest_index) + 1,
        status=status,
        current_step_name=current_step_name,
        next_step_name=next_step_name,
        plan_json=_safe_json(_safe_checkpoint_payload(plan)) if plan is not None else None,
        state_json=_safe_json(_safe_checkpoint_payload(state)),
        completed_steps_json=_safe_json(_safe_checkpoint_payload(completed_steps)),
        pending_steps_json=_safe_json(_safe_checkpoint_payload(pending_steps)),
        artifacts_json=_safe_json(_safe_checkpoint_payload(artifacts)) if artifacts is not None else None,
        created_at=datetime.now(UTC),
    )
    db.add(checkpoint)
    db.flush()
    return _checkpoint_record(checkpoint)


def get_latest_checkpoint(db: Session, run_id: str) -> AgentCheckpointRecord | None:
    checkpoint = _latest_checkpoint_model(db, run_id)
    return _checkpoint_record(checkpoint) if checkpoint is not None else None


def get_latest_checkpoint_payload(db: Session, run_id: str) -> dict[str, Any] | None:
    checkpoint = _latest_checkpoint_model(db, run_id)
    if checkpoint is None:
        return None
    return {
        "record": _checkpoint_record(checkpoint),
        "plan": _safe_checkpoint_payload(_parse_json_any(checkpoint.plan_json)),
        "state": _safe_checkpoint_payload(_parse_json_any(checkpoint.state_json)),
        "completed_steps": _safe_checkpoint_payload(
            _parse_json_any(checkpoint.completed_steps_json) or []
        ),
        "pending_steps": _safe_checkpoint_payload(
            _parse_json_any(checkpoint.pending_steps_json) or []
        ),
        "artifacts": _safe_checkpoint_payload(_parse_json_any(checkpoint.artifacts_json) or []),
    }


def list_checkpoints(db: Session, run_id: str) -> list[AgentCheckpointRecord]:
    checkpoints = (
        db.query(AgentCheckpoint)
        .filter(AgentCheckpoint.run_id == run_id)
        .order_by(AgentCheckpoint.checkpoint_index.asc())
        .all()
    )
    return [_checkpoint_record(checkpoint) for checkpoint in checkpoints]
