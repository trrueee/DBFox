"""Shared helpers and cross-entity converters for persistence submodules."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from engine.agent_core.types import (
    AgentApprovalRecord,
    AgentCheckpointRecord,
    AgentRunResponse,
    AgentRuntimeEvent,
)
from engine.models import AgentApproval, AgentCheckpoint

logger = logging.getLogger("dbfox.agent.persistence")

_SENSITIVE_KEYS = frozenset({
    "api_key", "api_base", "password", "token", "secret",
    "password_ciphertext", "password_nonce", "ssh_password_ciphertext",
    "ssh_password_nonce", "ssh_pkey_passphrase_ciphertext", "ssh_pkey_passphrase_nonce",
})


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


def _safe_event_payload(event: AgentRuntimeEvent) -> dict[str, Any]:
    data = event.model_dump()
    if event.step and isinstance(event.step, dict):
        data["step"] = {k: v for k, v in event.step.items() if k not in _SENSITIVE_KEYS}
    if event.response is not None:
        resp_data = event.response.model_dump()
        resp_data.pop("api_key", None)
        data["response"] = resp_data
    return data


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


def _redact_trace_event(
    event_data: dict[str, Any],
    _record: Any,
) -> dict[str, Any]:
    return _redact_trace_for_storage(event_data)


def _normalize_risk_level(risk_level: str | None) -> str:
    if risk_level in {"safe", "warning", "danger"}:
        return risk_level
    return "warning"


def _approval_record(approval: AgentApproval) -> AgentApprovalRecord:
    return AgentApprovalRecord(
        id=approval.id,
        run_id=approval.run_id,
        session_id=approval.session_id,
        step_name=approval.step_name,
        tool_name=approval.tool_name,
        status=approval.status,
        risk_level=_normalize_risk_level(approval.risk_level),
        reason=approval.reason,
        policy_decision=_parse_json(approval.policy_decision_json) or {},
        requested_action=_parse_json(approval.requested_action_json),
        created_at=approval.created_at,
        expires_at=approval.expires_at,
        decided_at=approval.decided_at,
        decided_by=approval.decided_by,
        decision_note=approval.decision_note,
    )


def _checkpoint_record(checkpoint: AgentCheckpoint) -> AgentCheckpointRecord:
    return AgentCheckpointRecord(
        id=checkpoint.id,
        run_id=checkpoint.run_id,
        session_id=checkpoint.session_id,
        checkpoint_index=checkpoint.checkpoint_index,
        status=checkpoint.status,
        current_step_name=checkpoint.current_step_name,
        next_step_name=checkpoint.next_step_name,
        created_at=checkpoint.created_at,
    )


def _restore_response(run: Any) -> AgentRunResponse | None:
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


def _load_run_artifacts(db: Session, run_id: str) -> list[Any]:
    from engine.models import AgentArtifactRecord
    return (
        db.query(AgentArtifactRecord)
        .filter(AgentArtifactRecord.run_id == run_id)
        .order_by(AgentArtifactRecord.sequence)
        .all()
    )


def _artifact_to_dict(r: Any) -> dict[str, Any]:
    """Convert an AgentArtifactRecord to a plain dict (shared by list + restore)."""
    return {
        "id": r.id,
        "run_id": r.run_id,
        "semantic_id": r.semantic_id,
        "type": r.type,
        "title": r.title,
        "produced_by_step": r.produced_by_step,
        "depends_on": (_parse_json(r.depends_on_json) or {}).get("depends_on", []),
        "payload": _parse_json(r.payload_json) or {},
        "presentation": _parse_json(r.presentation_json) or {},
        "refs": _parse_json(r.refs_json) or {},
        "sequence": r.sequence,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _summarize_artifact_payload(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("sql"), str):
        return str(payload["sql"])[:360]
    if "rowCount" in payload or "columns" in payload:
        columns = payload.get("columns") if isinstance(payload.get("columns"), list) else []
        return f"rowCount={payload.get('rowCount')}; columns={', '.join(str(c) for c in columns[:8])}"
    if "can_execute" in payload:
        return f"can_execute={payload.get('can_execute')}"
    if "error" in payload:
        return str(payload.get("error") or "")[:200]
    return ", ".join(f"{k}={v}" for k, v in list(payload.items())[:6])[:200]


def _to_timestamp_ms(dt: datetime | None) -> int:
    if dt is None:
        return int(datetime.now(UTC).timestamp() * 1000)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def _format_cell(val: Any) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, (str, int, float)):
        return str(val)
    return json.dumps(val, ensure_ascii=False)
