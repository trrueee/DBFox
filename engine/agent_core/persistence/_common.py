"""Shared helpers and cross-entity converters for persistence submodules."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.orm import Session

from engine.agent_core.types import (
    AgentApprovalRecord,
    AgentApprovalRiskLevel,
    AgentApprovalStatus,
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


def _parse_json_any(raw: Any) -> Any:
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _parse_json(raw: Any) -> dict[str, Any] | None:
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


def _model_value(record: Any, field: str, default: Any = None) -> Any:
    return getattr(record, field, default)


def _model_str(record: Any, field: str, default: str = "") -> str:
    value = _model_value(record, field, default)
    return default if value is None else str(value)


def _model_optional_str(record: Any, field: str) -> str | None:
    value = _model_value(record, field)
    return str(value) if value is not None else None


def _model_int(record: Any, field: str, default: int = 0) -> int:
    value = _model_value(record, field, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _model_datetime(record: Any, field: str) -> datetime | None:
    value = _model_value(record, field)
    return value if isinstance(value, datetime) else None


def _normalize_approval_status(status: str | None) -> AgentApprovalStatus:
    if status in {"pending", "approved", "rejected", "expired"}:
        return cast(AgentApprovalStatus, status)
    return "pending"


def _normalize_risk_level(risk_level: str | None) -> AgentApprovalRiskLevel:
    if risk_level in {"safe", "warning", "danger"}:
        return cast(AgentApprovalRiskLevel, risk_level)
    return "warning"


def _approval_record(approval: AgentApproval) -> AgentApprovalRecord:
    return AgentApprovalRecord(
        id=_model_str(approval, "id"),
        run_id=_model_str(approval, "run_id"),
        session_id=_model_str(approval, "session_id"),
        step_name=_model_str(approval, "step_name"),
        tool_name=_model_optional_str(approval, "tool_name"),
        status=_normalize_approval_status(_model_optional_str(approval, "status")),
        risk_level=_normalize_risk_level(_model_optional_str(approval, "risk_level")),
        reason=_model_optional_str(approval, "reason"),
        policy_decision=_parse_json(_model_optional_str(approval, "policy_decision_json")) or {},
        requested_action=_parse_json(_model_optional_str(approval, "requested_action_json")),
        created_at=_model_datetime(approval, "created_at") or datetime.now(UTC),
        expires_at=_model_datetime(approval, "expires_at"),
        decided_at=_model_datetime(approval, "decided_at"),
        decided_by=_model_optional_str(approval, "decided_by"),
        decision_note=_model_optional_str(approval, "decision_note"),
    )


def _checkpoint_record(checkpoint: AgentCheckpoint) -> AgentCheckpointRecord:
    return AgentCheckpointRecord(
        id=_model_str(checkpoint, "id"),
        run_id=_model_str(checkpoint, "run_id"),
        session_id=_model_str(checkpoint, "session_id"),
        checkpoint_index=_model_int(checkpoint, "checkpoint_index"),
        status=_model_str(checkpoint, "status"),
        current_step_name=_model_optional_str(checkpoint, "current_step_name"),
        next_step_name=_model_optional_str(checkpoint, "next_step_name"),
        created_at=_model_datetime(checkpoint, "created_at") or datetime.now(UTC),
    )


def _restore_response(run: Any) -> AgentRunResponse | None:
    response_json = _model_optional_str(run, "response_json")
    if response_json is None:
        return None
    data = _parse_json(response_json)
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
        "id": _model_str(r, "id"),
        "run_id": _model_str(r, "run_id"),
        "semantic_id": _model_str(r, "semantic_id"),
        "type": _model_str(r, "type"),
        "title": _model_str(r, "title"),
        "produced_by_step": _model_str(r, "produced_by_step"),
        "depends_on": (_parse_json(_model_optional_str(r, "depends_on_json")) or {}).get("depends_on", []),
        "payload": _parse_json(_model_optional_str(r, "payload_json")) or {},
        "presentation": _parse_json(_model_optional_str(r, "presentation_json")) or {},
        "refs": _parse_json(_model_optional_str(r, "refs_json")) or {},
        "sequence": _model_int(r, "sequence"),
        "created_at": (_model_datetime(r, "created_at") or datetime.now(UTC)).isoformat(),
    }


def _summarize_artifact_payload(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("sql"), str):
        return str(payload["sql"])[:360]
    if "rowCount" in payload or "columns" in payload:
        raw_columns = payload.get("columns")
        columns = raw_columns if isinstance(raw_columns, list) else []
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
