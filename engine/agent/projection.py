"""Canonical, independently paged conversation snapshot."""

from __future__ import annotations

from typing import Any

from engine.json_codec import JsonCodecError, loads

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.run_item import project_run
from engine.models import AgentRun, AgentRunItemRecord, AgentSession


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return loads(value or "")
    except JsonCodecError:
        return fallback


def conversation_snapshot(
    db: Session,
    session_id: str,
    *,
    item_limit: int = 200,
    run_limit: int = 20,
    before_item_sequence: int | None = None,
    before_run_sequence: int | None = None,
) -> dict[str, Any] | None:
    aggregate = db.get(AgentSession, session_id)
    if aggregate is None or aggregate.deleted_at is not None:
        return None

    run_query = select(AgentRun).where(AgentRun.session_id == session_id)
    if before_run_sequence is not None:
        run_query = run_query.where(AgentRun.session_sequence < before_run_sequence)
    run_page = list(db.execute(
        run_query.order_by(AgentRun.session_sequence.desc()).limit(run_limit + 1)
    ).scalars().all())
    has_more_runs = len(run_page) > run_limit
    runs = list(reversed(run_page[:run_limit]))

    item_query = select(AgentRunItemRecord).where(
        AgentRunItemRecord.session_id == session_id
    )
    if before_item_sequence is not None:
        item_query = item_query.where(
            AgentRunItemRecord.sequence < before_item_sequence
        )
    item_page = list(db.execute(
        item_query.order_by(AgentRunItemRecord.sequence.desc()).limit(item_limit + 1)
    ).scalars().all())
    has_more_items = len(item_page) > item_limit
    item_rows = list(reversed(item_page[:item_limit]))

    return {
        "protocol_version": 2,
        "session": {
            "id": str(aggregate.id),
            "project_id": str(aggregate.project_id) if aggregate.project_id else None,
            "datasource_id": str(aggregate.datasource_id) if aggregate.datasource_id else None,
            "title": str(aggregate.title),
            "context_epoch": int(aggregate.context_epoch or 0),
            "selected_artifact_id": (
                str(aggregate.selected_artifact_id)
                if aggregate.selected_artifact_id
                else None
            ),
            "context_tables": _loads(
                str(aggregate.context_tables_json or "[]"),
                [],
            ),
        },
        "runs": [project_run(row) for row in runs],
        "items": [
            _loads(str(row.item_json), {})
            for row in item_rows
        ],
        "pagination": {
            "items": {
                "has_more": has_more_items,
                "next_before_sequence": (
                    int(item_rows[0].sequence)
                    if has_more_items and item_rows
                    else None
                ),
            },
            "runs": {
                "has_more": has_more_runs,
                "next_before_sequence": (
                    int(runs[0].session_sequence)
                    if has_more_runs and runs
                    else None
                ),
            },
        },
        "cursor": int(aggregate.event_sequence or 0),
    }
