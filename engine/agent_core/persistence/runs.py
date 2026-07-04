"""Run lifecycle operations — start, complete, fail, cancel, query."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.orm import Session

from engine.errors import DBFoxError
from engine.agent_core.types import AgentArtifactType, AgentRunRequest, AgentRunResponse
from engine.models import AgentMessage, AgentRun, AgentArtifactRecord
from engine.agent_core.persistence._common import (
    _safe_json,
    _restore_response,
    _redact_response,
    _load_run_artifacts,
    _parse_json,
    _redact_trace_for_storage,
    _summarize_artifact_payload,
    _model_optional_str,
    _model_str,
)

logger = logging.getLogger("dbfox.agent.persistence")


def _next_message_sequence(db: Session, session_id: str) -> int:
    value = (
        db.query(AgentMessage.sequence)
        .filter(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.sequence.desc())
        .first()
    )
    return int(value[0]) + 1 if value else 1


def _answer_text(response: AgentRunResponse) -> str:
    if response.answer and response.answer.answer.strip():
        return response.answer.answer.strip()
    if response.explanation and response.explanation.strip():
        return response.explanation.strip()
    if response.error and response.error.strip():
        return f"执行未完成：{response.error}"
    return "已完成。"


def _update_assistant_message(
    db: Session,
    run: AgentRun,
    *,
    content: str,
    status: str,
) -> None:
    assistant = db.get(AgentMessage, run.assistant_message_id) if run.assistant_message_id else None
    if assistant is None:
        return
    assistant.content = content  # type: ignore[assignment]
    assistant.status = status  # type: ignore[assignment]
    assistant.updated_at = datetime.now(UTC)  # type: ignore[assignment]


def start_run(
    db: Session,
    req: AgentRunRequest,
    run_id: str,
    session_id: str,
) -> None:
    now = datetime.now(UTC)
    user_message_id = req.user_message_id or f"msg-user-{uuid4()}"
    assistant_message_id = req.assistant_message_id or f"msg-assistant-{uuid4()}"
    sequence = _next_message_sequence(db, session_id)
    db.add(
        AgentMessage(
            id=user_message_id,
            session_id=session_id,
            role="user",
            content=req.question,
            status="completed",
            sequence=sequence,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        AgentMessage(
            id=assistant_message_id,
            session_id=session_id,
            role="assistant",
            content="",
            status="streaming",
            sequence=sequence + 1,
            created_at=now,
            updated_at=now,
        )
    )
    run = AgentRun(
        id=run_id,
        session_id=session_id,
        parent_run_id=req.parent_run_id or (
            req.follow_up_context.parent_run_id if req.follow_up_context else None
        ),
        datasource_id=req.datasource_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        question=req.question,
        status="running",
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()


def complete_run(db: Session, response: AgentRunResponse) -> None:
    try:
        run = db.query(AgentRun).filter(AgentRun.id == response.run_id).first()
        if run is None:
            logger.warning("Cannot complete run %s: run not found", response.run_id)
            return
        run.status = response.status or ("completed" if response.success else "failed")  # type: ignore[assignment]
        run.current_step_name = None  # type: ignore[assignment]
        run.waiting_approval_id = None  # type: ignore[assignment]
        run.response_json = _safe_json(_redact_response(response))  # type: ignore[assignment]
        run.context_summary = response.context_summary  # type: ignore[assignment]
        run.error = response.error  # type: ignore[assignment]
        run.error_message = response.error  # type: ignore[assignment]
        run.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        run.updated_at = datetime.now(UTC)  # type: ignore[assignment]
        _update_assistant_message(
            db,
            run,
            content=_answer_text(response),
            status="completed" if response.success else "failed",
        )
        db.flush()
        _save_trace_events(db, response)
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
        run.error_message = error  # type: ignore[assignment]
        if response is not None:
            run.response_json = _safe_json(_redact_response(response))  # type: ignore[assignment]
            run.context_summary = response.context_summary  # type: ignore[assignment]
        run.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        run.updated_at = datetime.now(UTC)  # type: ignore[assignment]
        _update_assistant_message(
            db,
            run,
            content=_answer_text(response) if response is not None else f"执行未完成：{error}",
            status="failed",
        )
        db.flush()
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
        run.error_message = "User cancelled the agent run."  # type: ignore[assignment]
        run.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        run.updated_at = datetime.now(UTC)  # type: ignore[assignment]
        _update_assistant_message(
            db,
            run,
            content="已取消。",
            status="cancelled",
        )
        db.flush()
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


def mark_run_resumed(db: Session, *, run_id: str, current_step_name: str | None = "execute_readonly") -> None:
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


def _response_evidence_ids(response_data: dict[str, Any] | None) -> set[str]:
    if not isinstance(response_data, dict):
        return set()
    answer = response_data.get("answer")
    if not isinstance(answer, dict):
        return set()
    evidence = answer.get("evidence")
    if not isinstance(evidence, list):
        return set()
    ids: set[str] = set()
    for item in evidence:
        if isinstance(item, dict) and isinstance(item.get("artifact_id"), str):
            ids.add(item["artifact_id"])
    return ids


def _payload_has_rows(payload: dict[str, Any]) -> bool:
    rows = payload.get("rows") or payload.get("previewRows")
    if isinstance(rows, list) and rows:
        return True
    for key in ("rowCount", "returnedRows", "returned_rows", "previewRowCount"):
        value = payload.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            return int(value) > 0
        except (TypeError, ValueError):
            continue
    return False


def _is_followup_artifact(artifact: Any, payload: dict[str, Any]) -> bool:
    artifact_type = str(artifact.type or "")
    if artifact_type == "result_view":
        return _payload_has_rows(payload)
    if artifact_type == "chart":
        return True
    if artifact_type == "sql":
        safety = payload.get("safety_state")
        if isinstance(safety, dict) and safety.get("can_execute") is False:
            return False
        if str(payload.get("execution_status") or "") == "failed":
            return False
        return bool(payload.get("sql") or payload.get("safeSql") or payload.get("safe_sql"))
    return False


def _select_followup_artifacts(
    artifacts: list[Any],
    response_data: dict[str, Any] | None,
) -> list[tuple[Any, dict[str, Any]]]:
    evidence_ids = _response_evidence_ids(response_data)
    selected: list[tuple[Any, dict[str, Any]]] = []
    for artifact in artifacts:
        payload = _parse_json(artifact.payload_json) or {}
        if _is_followup_artifact(artifact, payload):
            selected.append((artifact, payload))

    type_rank = {"result_view": 0, "chart": 1, "sql": 2}

    def rank(item: tuple[Any, dict[str, Any]]) -> tuple[int, int, int]:
        artifact, _payload = item
        artifact_ids = {str(artifact.id or ""), str(artifact.semantic_id or "")}
        evidence_rank = 0 if artifact_ids.intersection(evidence_ids) else 1
        sequence = artifact.sequence if isinstance(artifact.sequence, int) else 10_000
        return (evidence_rank, type_rank.get(str(artifact.type or ""), 9), sequence)

    return sorted(selected, key=rank)


def build_followup_context_from_run(
    db: Session,
    parent_run_id: str,
) -> Any:
    from engine.agent_core.types import AgentFollowUpContext, AgentContextArtifact
    run = db.query(AgentRun).filter(AgentRun.id == parent_run_id).first()
    if run is None:
        return None

    response_json = _model_optional_str(run, "response_json")
    response_data = _parse_json(response_json) if response_json else None
    previous_answer = None
    if response_data:
        answer = response_data.get("answer")
        if isinstance(answer, dict):
            previous_answer = answer.get("answer")
        if not previous_answer:
            previous_answer = response_data.get("explanation")

    artifacts = _select_followup_artifacts(
        _load_run_artifacts(db, parent_run_id),
        response_data,
    )

    return AgentFollowUpContext(
        session_id=_model_optional_str(run, "session_id"),
        parent_run_id=_model_optional_str(run, "id"),
        previous_question=_model_optional_str(run, "question"),
        previous_answer=previous_answer,
        artifacts=[
            AgentContextArtifact(
                id=_model_str(artifact, "id"),
                type=cast(AgentArtifactType, _model_str(artifact, "type")),
                title=_model_str(artifact, "title"),
                summary=_summarize_artifact_payload(
                    payload
                ),
                payload=payload,
            )
            for artifact, payload in artifacts[:6]
        ],
    )
