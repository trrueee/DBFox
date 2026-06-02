from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from engine.agent.types import (
    AgentArtifact,
    AgentAnswer,
    AgentArtifactPresentation,
    AgentContextArtifact,
    AgentFollowUpContext,
    AgentRunRequest,
    AgentRunResponse,
    AgentRuntimeEvent,
    AgentStep,
    AgentTraceEvent,
    AgentVisibleEvent,
    FollowUpSuggestion,
    ResultProfile,
)
from engine.models import (
    AgentArtifactRecord,
    AgentRun,
    AgentRuntimeEventRecord,
    AgentSession,
    AgentTraceEventRecord,
)

logger = logging.getLogger("databox.agent.persistence")


def _safe_json(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "{}"
    return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_json(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


_SENSITIVE_KEYS = frozenset({
    "api_key", "api_base", "password", "token", "secret",
    "password_ciphertext", "password_nonce", "ssh_password_ciphertext",
    "ssh_password_nonce", "ssh_pkey_passphrase_ciphertext", "ssh_pkey_passphrase_nonce",
})


def _safe_event_payload(event: AgentRuntimeEvent) -> dict[str, Any]:
    data = event.model_dump()
    if event.step and isinstance(event.step, dict):
        data["step"] = {k: v for k, v in event.step.items() if k not in _SENSITIVE_KEYS}
    if event.response is not None:
        resp_data = event.response.model_dump()
        resp_data.pop("api_key", None)
        data["response"] = resp_data
    return data


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
        existing.updated_at = datetime.now(UTC)
        db.flush()
    return session_id


def _resolve_session_id(req: AgentRunRequest) -> str:
    if req.session_id:
        return req.session_id
    if req.follow_up_context and req.follow_up_context.session_id:
        return req.follow_up_context.session_id
    from uuid import uuid4
    return str(uuid4())


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
    except Exception:
        logger.exception("Failed to record runtime event %s", event.event_id)


def record_artifact(
    db: Session,
    session_id: str,
    run_id: str,
    artifact: AgentArtifact,
    sequence: int | None = None,
) -> None:
    try:
        record = AgentArtifactRecord(
            id=artifact.id,
            run_id=run_id,
            session_id=session_id,
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
            sequence=sequence,
            created_at=datetime.now(UTC),
        )
        db.add(record)
        db.flush()
    except Exception:
        logger.exception("Failed to record artifact %s", artifact.id)


def complete_run(db: Session, response: AgentRunResponse) -> None:
    try:
        run = db.query(AgentRun).filter(AgentRun.id == response.run_id).first()
        if run is None:
            logger.warning("Cannot complete run %s: run not found", response.run_id)
            return
        run.status = "success" if response.success else "failed"
        run.response_json = _safe_json(_redact_response(response))
        run.context_summary = response.context_summary
        run.error = response.error
        run.completed_at = datetime.now(UTC)
        run.updated_at = datetime.now(UTC)
        db.flush()
    except Exception:
        logger.exception("Failed to complete run %s", response.run_id)


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
        run.status = "failed"
        run.error = error
        if response is not None:
            run.response_json = _safe_json(_redact_response(response))
            run.context_summary = response.context_summary
        run.completed_at = datetime.now(UTC)
        run.updated_at = datetime.now(UTC)
        db.flush()
    except Exception:
        logger.exception("Failed to record failure for run %s", run_id)


def get_run(db: Session, run_id: str) -> AgentRunResponse | None:
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run is None or run.response_json is None:
        return None
    return _restore_response(run)


def list_session_runs(db: Session, session_id: str) -> list[dict[str, Any]]:
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.session_id == session_id)
        .order_by(AgentRun.created_at.desc())
        .all()
    )
    return [
        {
            "run_id": r.id,
            "session_id": r.session_id,
            "parent_run_id": r.parent_run_id,
            "question": r.question,
            "status": r.status,
            "error": r.error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


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


def build_followup_context_from_run(
    db: Session,
    parent_run_id: str,
) -> AgentFollowUpContext | None:
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
                type=artifact.type,  # type: ignore[arg-type]
                title=artifact.title,
                summary=_summarize_artifact_payload(
                    _parse_json(artifact.payload_json) or {}
                ),
                payload=_parse_json(artifact.payload_json) or {},
            )
            for artifact in artifacts[:8]
        ],
    )


def _load_run_artifacts(db: Session, run_id: str) -> list[AgentArtifactRecord]:
    return (
        db.query(AgentArtifactRecord)
        .filter(AgentArtifactRecord.run_id == run_id)
        .order_by(AgentArtifactRecord.sequence)
        .all()
    )


def _restore_response(run: AgentRun) -> AgentRunResponse | None:
    if run.response_json is None:
        return None
    data = _parse_json(run.response_json)
    if data is None:
        return None
    return AgentRunResponse.model_validate(data)


def _redact_response(response: AgentRunResponse) -> dict[str, Any]:
    data = response.model_dump()
    data.pop("api_key", None)
    if "follow_up_context" in data:
        data.pop("follow_up_context", None)
    return data


def _summarize_artifact_payload(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("sql"), str):
        return str(payload["sql"])[:360]
    if "rowCount" in payload or "columns" in payload:
        columns = payload.get("columns") if isinstance(payload.get("columns"), list) else []
        return f"rowCount={payload.get('rowCount')}; columns={', '.join(str(c) for c in columns[:8])}"
    if "notable_facts" in payload:
        facts = payload.get("notable_facts") if isinstance(payload.get("notable_facts"), list) else []
        return "; ".join(str(f) for f in facts[:4])
    if "can_execute" in payload:
        return f"can_execute={payload.get('can_execute')}"
    if "error" in payload:
        return str(payload.get("error") or "")[:200]
    return ", ".join(f"{k}={v}" for k, v in list(payload.items())[:6])[:200]
