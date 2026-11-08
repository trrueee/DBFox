from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from engine.agent.artifact import Artifact
from engine.agent.projection import conversation_snapshot
from engine.agent.run import TERMINAL_RUN_STATUSES
from engine.agent.repositories.artifact import ArtifactRepository
from engine.db import get_db
from engine.json_codec import loads as json_loads
from engine.models import AgentEvidenceRecord, AgentRun, AgentSession
from engine.schemas.api_responses import (
    ConversationSnapshotResponse,
    ConversationSummaryResponse,
    EvidenceResponse,
)
from engine.api.conversation_common import required_iso


router = APIRouter()


@router.get("/conversations", response_model=list[ConversationSummaryResponse])
def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    # Match the workspace: the oldest unfinished Run owns intervention; queued
    # follow-ups must not hide it. With no unfinished work, show the latest Run.
    unfinished = AgentRun.status.not_in([status.value for status in TERMINAL_RUN_STATUSES])
    run_status = (
        select(AgentRun.status)
        .where(AgentRun.session_id == AgentSession.id)
        .order_by(
            case((unfinished, 0), else_=1),
            case((unfinished, AgentRun.session_sequence), else_=-AgentRun.session_sequence),
        )
        .limit(1)
        .correlate(AgentSession)
        .scalar_subquery()
    )
    # Workbench actions retain their canonical Session/Run and Artifact history.
    # Terminal action-only Sessions are not chat threads; unfinished work must
    # remain reachable for intervention, and a real follow-up makes a chat visible.
    has_runs = select(AgentRun.id).where(AgentRun.session_id == AgentSession.id).exists()
    has_chat_or_unfinished_run = (
        select(AgentRun.id)
        .where(
            AgentRun.session_id == AgentSession.id,
            or_(
                func.json_extract(AgentRun.request_json, "$.source").is_distinct_from("dlc_workbench_action"),
                unfinished,
            ),
        )
        .exists()
    )
    rows = db.execute(
        select(AgentSession, run_status.label("run_status"))
        .where(AgentSession.deleted_at.is_(None), or_(~has_runs, has_chat_or_unfinished_run))
        .order_by(AgentSession.updated_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        {
            "id": str(row.id),
            "project_id": str(row.project_id) if row.project_id else None,
            "title": str(row.title),
            "selected_artifact_id": (
                str(row.selected_artifact_id) if row.selected_artifact_id else None
            ),
            "updated_at": required_iso(row.updated_at, "updated_at"),
            "run_status": status,
            "cursor": int(row.event_sequence),
        }
        for row, status in rows
    ]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationSnapshotResponse,
)
def get_conversation(
    conversation_id: str,
    item_limit: int = Query(default=200, ge=1, le=1_000),
    run_limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    detail = conversation_snapshot(
        db,
        conversation_id,
        item_limit=item_limit,
        run_limit=run_limit,
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."},
        )
    return detail


@router.get(
    "/conversations/{conversation_id}/history",
    response_model=ConversationSnapshotResponse,
)
def get_conversation_history(
    conversation_id: str,
    before_item_sequence: int | None = Query(default=None, ge=1),
    before_run_sequence: int | None = Query(default=None, ge=1),
    item_limit: int = Query(default=200, ge=1, le=1_000),
    run_limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    detail = conversation_snapshot(
        db,
        conversation_id,
        item_limit=item_limit,
        run_limit=run_limit,
        before_item_sequence=before_item_sequence,
        before_run_sequence=before_run_sequence,
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."},
        )
    return detail


@router.get(
    "/conversations/{conversation_id}/runs/{run_id}/artifacts",
    response_model=list[Artifact],
)
def get_run_artifacts(
    conversation_id: str,
    run_id: str,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    run = db.get(AgentRun, run_id)
    if run is None or str(run.session_id) != conversation_id:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
    return [
        item.model_dump(mode="json")
        for item in ArtifactRepository(db).list_for_run(run_id)
    ]


@router.get(
    "/conversations/{conversation_id}/runs/{run_id}/evidence",
    response_model=list[EvidenceResponse],
)
def get_run_evidence(
    conversation_id: str,
    run_id: str,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    run = db.get(AgentRun, run_id)
    if run is None or str(run.session_id) != conversation_id:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
    rows = db.execute(
        select(AgentEvidenceRecord)
        .where(AgentEvidenceRecord.run_id == run_id)
        .order_by(AgentEvidenceRecord.created_at)
    ).scalars().all()
    return [
        {
            "id": str(row.id),
            "session_id": str(row.session_id),
            "run_id": str(row.run_id),
            "claim_id": str(row.claim_id),
            "artifact_id": str(row.artifact_id),
            "label": str(row.label),
            "observed_at": required_iso(row.observed_at, "observed_at"),
            "locator": json_loads(str(row.locator_json or "{}")),
            "value": json_loads(str(row.value_json)) if row.value_json else None,
        }
        for row in rows
    ]
