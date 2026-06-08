from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from engine.errors import DataBoxError
from engine.agent.types import (
    AgentArtifact,
    AgentAnswer,
    AgentArtifactPresentation,
    AgentApprovalRecord,
    AgentCheckpointRecord,
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
    AgentApproval,
    AgentArtifactRecord,
    AgentCheckpoint,
    AgentRun,
    AgentRuntimeEventRecord,
    AgentSession,
    AgentTraceEventRecord,
)

logger = logging.getLogger("databox.agent.persistence")


def _safe_json(payload: Any | None) -> str:
    if payload is None:
        return "{}"
    return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_json_any(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _parse_json(raw: str | None) -> dict[str, Any] | None:
    parsed = _parse_json_any(raw)
    return parsed if isinstance(parsed, dict) else None


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
        existing.updated_at = datetime.now(UTC)  # type: ignore[assignment]
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
    except Exception:
        logger.exception("Failed to complete run %s", response.run_id)


def _save_trace_events(db: Session, response: AgentRunResponse) -> None:
    if not response.trace_events:
        return
    for idx, trace in enumerate(response.trace_events):
        try:
            record = AgentTraceEventRecord(
                id=f"trace_{response.run_id[:8]}_{idx}_{trace.sequence or idx}",
                run_id=response.run_id,
                session_id=response.session_id,
                sequence=trace.sequence or idx + 1,
                type=trace.type,
                event_json=_safe_json(_redact_trace_for_storage(trace.model_dump())),
                created_at_ms=0,
                created_at=datetime.now(UTC),
            )
            db.add(record)
        except Exception:
            logger.warning("Failed to save trace event %s", trace.event_id)
    db.flush()


def _redact_trace_for_storage(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, v in data.items():
        if k in _SENSITIVE_KEYS:
            continue
        if isinstance(v, dict):
            result[k] = _redact_trace_for_storage(v)
        elif isinstance(v, list):
            result[k] = [
                _redact_trace_for_storage(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


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
    except Exception:
        logger.exception("Failed to record failure for run %s", run_id)


def create_approval(
    db: Session,
    *,
    run_id: str,
    session_id: str,
    step_name: str,
    tool_name: str | None,
    risk_level: str,
    reason: str | None,
    policy_decision: dict[str, Any],
    requested_action: dict[str, Any] | None = None,
    expires_at: datetime | None = None,
) -> AgentApprovalRecord:
    approval = AgentApproval(
        id=f"approval_{uuid.uuid4().hex}",
        run_id=run_id,
        session_id=session_id,
        step_name=step_name,
        tool_name=tool_name,
        status="pending",
        risk_level=_normalize_risk_level(risk_level),
        reason=reason,
        policy_decision_json=_safe_json(policy_decision),
        requested_action_json=_safe_json(requested_action) if requested_action is not None else None,
        created_at=datetime.now(UTC),
        expires_at=expires_at,
    )
    db.add(approval)
    db.flush()
    return _approval_record(approval)


def get_approval(db: Session, approval_id: str) -> AgentApprovalRecord | None:
    approval = db.query(AgentApproval).filter(AgentApproval.id == approval_id).first()
    return _approval_record(approval) if approval is not None else None


def get_pending_approval_for_run(db: Session, run_id: str) -> AgentApprovalRecord | None:
    approval = (
        db.query(AgentApproval)
        .filter(AgentApproval.run_id == run_id, AgentApproval.status == "pending")
        .order_by(AgentApproval.created_at.desc())
        .first()
    )
    return _approval_record(approval) if approval is not None else None


def list_run_approvals(db: Session, run_id: str) -> list[AgentApprovalRecord]:
    approvals = (
        db.query(AgentApproval)
        .filter(AgentApproval.run_id == run_id)
        .order_by(AgentApproval.created_at.asc())
        .all()
    )
    return [_approval_record(approval) for approval in approvals]


def resolve_approval(
    db: Session,
    *,
    run_id: str,
    approval_id: str,
    decision: str,
    note: str | None = None,
    decided_by: str | None = "local-user",
) -> AgentApprovalRecord:
    if decision not in {"approved", "rejected"}:
        raise DataBoxError("Invalid approval decision.", code="INVALID_APPROVAL_DECISION")

    approval = db.query(AgentApproval).filter(AgentApproval.id == approval_id).first()
    if approval is None:
        raise DataBoxError("Approval not found.", code="APPROVAL_NOT_FOUND")
    if approval.run_id != run_id:
        raise DataBoxError("Approval does not belong to this run.", code="APPROVAL_RUN_MISMATCH")
    if approval.status != "pending":
        raise DataBoxError("Approval has already been resolved.", code="APPROVAL_ALREADY_RESOLVED")

    approval.status = decision  # type: ignore[assignment]
    approval.decided_by = decided_by  # type: ignore[assignment]
    approval.decision_note = note  # type: ignore[assignment]
    approval.decided_at = datetime.now(UTC)  # type: ignore[assignment]

    if decision == "rejected":
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run is not None:
            run.status = "failed"  # type: ignore[assignment]
            run.error = "Approval rejected"  # type: ignore[assignment]
            run.current_step_name = None  # type: ignore[assignment]
            run.waiting_approval_id = None  # type: ignore[assignment]
            run.completed_at = datetime.now(UTC)  # type: ignore[assignment]
            run.updated_at = datetime.now(UTC)  # type: ignore[assignment]

    db.flush()
    return _approval_record(approval)


def expire_approval(
    db: Session,
    *,
    approval_id: str,
    note: str,
    decided_by: str | None = "agent-kernel",
) -> AgentApprovalRecord | None:
    approval = db.query(AgentApproval).filter(AgentApproval.id == approval_id).first()
    if approval is None:
        return None
    if approval.status != "pending":
        return _approval_record(approval)

    approval.status = "expired"  # type: ignore[assignment]
    approval.decided_by = decided_by  # type: ignore[assignment]
    approval.decision_note = note  # type: ignore[assignment]
    approval.decided_at = datetime.now(UTC)  # type: ignore[assignment]

    run = db.query(AgentRun).filter(AgentRun.id == approval.run_id).first()
    if run is not None and run.waiting_approval_id == approval.id:
        run.waiting_approval_id = None  # type: ignore[assignment]
        run.current_step_name = None  # type: ignore[assignment]
        run.updated_at = datetime.now(UTC)  # type: ignore[assignment]

    db.flush()
    return _approval_record(approval)


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
        plan_json=_safe_json(plan) if plan is not None else None,
        state_json=_safe_json(state),
        completed_steps_json=_safe_json(completed_steps),
        pending_steps_json=_safe_json(pending_steps),
        artifacts_json=_safe_json(artifacts) if artifacts is not None else None,
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
        "plan": _parse_json_any(checkpoint.plan_json),  # type: ignore[arg-type]
        "state": _parse_json_any(checkpoint.state_json),  # type: ignore[arg-type]
        "completed_steps": _parse_json_any(checkpoint.completed_steps_json) or [],  # type: ignore[arg-type]
        "pending_steps": _parse_json_any(checkpoint.pending_steps_json) or [],  # type: ignore[arg-type]
        "artifacts": _parse_json_any(checkpoint.artifacts_json) or [],  # type: ignore[arg-type]
    }


def list_checkpoints(db: Session, run_id: str) -> list[AgentCheckpointRecord]:
    checkpoints = (
        db.query(AgentCheckpoint)
        .filter(AgentCheckpoint.run_id == run_id)
        .order_by(AgentCheckpoint.checkpoint_index.asc())
        .all()
    )
    return [_checkpoint_record(checkpoint) for checkpoint in checkpoints]


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
        raise DataBoxError("Agent run not found.", code="RUN_NOT_FOUND")
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


def mark_run_resumed(db: Session, *, run_id: str, current_step_name: str | None = "execute_sql") -> None:
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run is None:
        raise DataBoxError("Agent run not found.", code="RUN_NOT_FOUND")
    run.status = "running"  # type: ignore[assignment]
    run.current_step_name = current_step_name  # type: ignore[assignment]
    run.waiting_approval_id = None  # type: ignore[assignment]
    run.error = None  # type: ignore[assignment]
    run.completed_at = None  # type: ignore[assignment]
    run.updated_at = datetime.now(UTC)  # type: ignore[assignment]
    db.flush()


def get_latest_runtime_event_sequence(db: Session, run_id: str) -> int:
    latest = (
        db.query(func.max(AgentRuntimeEventRecord.sequence))
        .filter(AgentRuntimeEventRecord.run_id == run_id)
        .scalar()
        or 0
    )
    return int(latest)


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


def build_followup_context_from_run(
    db: Session,
    parent_run_id: str,
) -> AgentFollowUpContext | None:
    run = db.query(AgentRun).filter(AgentRun.id == parent_run_id).first()
    if run is None:
        return None

    artifacts = _load_run_artifacts(db, parent_run_id)

    response_data = _parse_json(run.response_json) if run.response_json else None  # type: ignore[arg-type]
    previous_answer = None
    if response_data:
        answer = response_data.get("answer")
        if isinstance(answer, dict):
            previous_answer = answer.get("answer")
        if not previous_answer:
            previous_answer = response_data.get("explanation")

    return AgentFollowUpContext(
        session_id=run.session_id,  # type: ignore[arg-type]
        parent_run_id=run.id,  # type: ignore[arg-type]
        previous_question=run.question,  # type: ignore[arg-type]
        previous_answer=previous_answer,
        artifacts=[
            AgentContextArtifact(
                id=artifact.id,  # type: ignore[arg-type]
                type=artifact.type,  # type: ignore[arg-type]
                title=artifact.title,  # type: ignore[arg-type]
                summary=_summarize_artifact_payload(
                    _parse_json(artifact.payload_json) or {}  # type: ignore[arg-type]
                ),
                payload=_parse_json(artifact.payload_json) or {},  # type: ignore[arg-type]
            )
            for artifact in artifacts[:8]
        ],
    )


def list_run_artifacts(db: Session, run_id: str) -> list[dict[str, Any]]:
    records = (
        db.query(AgentArtifactRecord)
        .filter(AgentArtifactRecord.run_id == run_id)
        .order_by(AgentArtifactRecord.sequence)
        .all()
    )
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "semantic_id": r.semantic_id,
            "type": r.type,
            "title": r.title,
            "produced_by_step": r.produced_by_step,
            "depends_on": (_parse_json(r.depends_on_json) or {}).get("depends_on", []),  # type: ignore[arg-type]
            "payload": _parse_json(r.payload_json) or {},  # type: ignore[arg-type]
            "presentation": _parse_json(r.presentation_json) or {},  # type: ignore[arg-type]
            "refs": _parse_json(r.refs_json) or {},  # type: ignore[arg-type]
            "sequence": r.sequence,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


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
            "event": _parse_json(r.event_json) or {},  # type: ignore[arg-type]
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
        _redact_trace_event(_parse_json(r.event_json) or {}, r)  # type: ignore[arg-type]
        for r in records
    ]


def restore_artifact(db: Session, artifact_id: str) -> dict[str, Any] | None:
    record = db.query(AgentArtifactRecord).filter(AgentArtifactRecord.id == artifact_id).first()
    if record is None:
        return None
    return {
        "id": record.id,
        "run_id": record.run_id,
        "semantic_id": record.semantic_id,
        "type": record.type,
        "title": record.title,
        "produced_by_step": record.produced_by_step,
        "depends_on": (_parse_json(record.depends_on_json) or {}).get("depends_on", []),  # type: ignore[arg-type]
        "payload": _parse_json(record.payload_json) or {},  # type: ignore[arg-type]
        "presentation": _parse_json(record.presentation_json) or {},  # type: ignore[arg-type]
        "refs": _parse_json(record.refs_json) or {},  # type: ignore[arg-type]
        "sequence": record.sequence,
    }


def restore_runtime_event(db: Session, event_id: str) -> dict[str, Any] | None:
    record = db.query(AgentRuntimeEventRecord).filter(AgentRuntimeEventRecord.id == event_id).first()
    if record is None:
        return None
    return {
        "id": record.id,
        "run_id": record.run_id,
        "sequence": record.sequence,
        "type": record.type,
        "event": _parse_json(record.event_json) or {},  # type: ignore[arg-type]
        "created_at_ms": record.created_at_ms,
    }


def _latest_checkpoint_model(db: Session, run_id: str) -> AgentCheckpoint | None:
    return (
        db.query(AgentCheckpoint)
        .filter(AgentCheckpoint.run_id == run_id)
        .order_by(AgentCheckpoint.checkpoint_index.desc(), AgentCheckpoint.created_at.desc())
        .first()
    )


def _approval_record(approval: AgentApproval) -> AgentApprovalRecord:
    return AgentApprovalRecord(
        id=approval.id,  # type: ignore[arg-type]
        run_id=approval.run_id,  # type: ignore[arg-type]
        session_id=approval.session_id,  # type: ignore[arg-type]
        step_name=approval.step_name,  # type: ignore[arg-type]
        tool_name=approval.tool_name,  # type: ignore[arg-type]
        status=approval.status,  # type: ignore[arg-type]
        risk_level=_normalize_risk_level(approval.risk_level),  # type: ignore[arg-type]
        reason=approval.reason,  # type: ignore[arg-type]
        policy_decision=_parse_json(approval.policy_decision_json) or {},  # type: ignore[arg-type]
        requested_action=_parse_json(approval.requested_action_json),  # type: ignore[arg-type]
        created_at=approval.created_at,  # type: ignore[arg-type]
        expires_at=approval.expires_at,  # type: ignore[arg-type]
        decided_at=approval.decided_at,  # type: ignore[arg-type]
        decided_by=approval.decided_by,  # type: ignore[arg-type]
        decision_note=approval.decision_note,  # type: ignore[arg-type]
    )


def _checkpoint_record(checkpoint: AgentCheckpoint) -> AgentCheckpointRecord:
    return AgentCheckpointRecord(
        id=checkpoint.id,  # type: ignore[arg-type]
        run_id=checkpoint.run_id,  # type: ignore[arg-type]
        session_id=checkpoint.session_id,  # type: ignore[arg-type]
        checkpoint_index=checkpoint.checkpoint_index,  # type: ignore[arg-type]
        status=checkpoint.status,  # type: ignore[arg-type]
        current_step_name=checkpoint.current_step_name,  # type: ignore[arg-type]
        next_step_name=checkpoint.next_step_name,  # type: ignore[arg-type]
        created_at=checkpoint.created_at,  # type: ignore[arg-type]
    )


def _normalize_risk_level(risk_level: str | None) -> str:
    if risk_level in {"safe", "warning", "danger"}:
        return risk_level
    return "warning"


def _redact_trace_event(
    event_data: dict[str, Any],
    _record: AgentTraceEventRecord,
) -> dict[str, Any]:
    return _redact_trace_for_storage(event_data)


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
    data = _parse_json(run.response_json)  # type: ignore[arg-type]
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
        return f"rowCount={payload.get('rowCount')}; columns={', '.join(str(c) for c in columns[:8])}"  # type: ignore[index]
    if "notable_facts" in payload:
        facts = payload.get("notable_facts") if isinstance(payload.get("notable_facts"), list) else []
        return "; ".join(str(f) for f in facts[:4])  # type: ignore[index]
    if "can_execute" in payload:
        return f"can_execute={payload.get('can_execute')}"
    if "error" in payload:
        return str(payload.get("error") or "")[:200]
    return ", ".join(f"{k}={v}" for k, v in list(payload.items())[:6])[:200]
