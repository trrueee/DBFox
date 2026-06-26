"""Shared helpers and cross-entity converters for persistence submodules."""
from __future__ import annotations

import json
import logging
import re
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
from engine.policy.redactor import DataRedactor

logger = logging.getLogger("dbfox.agent.persistence")

_SENSITIVE_KEYS = frozenset({
    "api_key", "api_base", "password", "token", "secret",
    "password_ciphertext", "password_nonce", "ssh_password_ciphertext",
    "ssh_password_nonce", "ssh_pkey_passphrase_ciphertext", "ssh_pkey_passphrase_nonce",
})
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "password",
    "passwd",
    "token",
    "secret",
    "credential",
    "passphrase",
    "private_key",
    "privatekey",
    "ciphertext",
    "nonce",
)
_SQL_KEY_PARTS = ("sql", "query")
_SQL_LITERAL_PATTERN = re.compile(r"'(?:''|[^'])*'")
_ARTIFACT_EXECUTABLE_SQL_KEYS = frozenset({"sql", "safeSql", "safe_sql", "sourceSql", "source_sql"})


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


def _redact_runtime_event_value(value: Any, key: str = "") -> Any:
    key_lower = key.lower()
    if key_lower in _SENSITIVE_KEYS or any(part in key_lower for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): _redact_runtime_event_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_runtime_event_value(item, key) for item in value]
    if isinstance(value, str):
        redacted = DataRedactor.redact_sql(value)
        if any(part in key_lower for part in _SQL_KEY_PARTS):
            redacted = _SQL_LITERAL_PATTERN.sub("'[REDACTED_LITERAL]'", redacted)
        return redacted
    return value


def _safe_artifact_payload(payload: Any) -> Any:
    return _redact_artifact_value(payload)


def _safe_checkpoint_payload(payload: Any) -> Any:
    return _redact_artifact_value(payload)


def _redact_artifact_value(value: Any, key: str = "") -> Any:
    key_lower = key.lower()
    if key in _ARTIFACT_EXECUTABLE_SQL_KEYS:
        return value
    if key_lower in _SENSITIVE_KEYS or any(part in key_lower for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        columns = _artifact_column_names(value.get("columns"))
        redacted: dict[str, Any] = {}
        for item_key, item_value in value.items():
            item_key_str = str(item_key)
            if item_key_str in {"rows", "previewRows", "preview_rows", "sampleRows", "sample_rows"}:
                redacted[item_key_str] = _redact_artifact_rows(item_value, columns)
            else:
                redacted[item_key_str] = _redact_artifact_value(item_value, item_key_str)
        return redacted
    if isinstance(value, list):
        return [_redact_artifact_value(item, key) for item in value]
    if isinstance(value, str):
        return DataRedactor.redact_sql(value)
    return value


def _artifact_column_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    columns: list[str] = []
    for item in value:
        if isinstance(item, str):
            columns.append(item)
        elif isinstance(item, dict):
            columns.append(str(item.get("name") or ""))
        else:
            columns.append("")
    return columns


def _redact_artifact_rows(value: Any, columns: list[str]) -> Any:
    if not isinstance(value, list):
        return _redact_artifact_value(value)
    redacted_rows: list[Any] = []
    for row in value:
        if isinstance(row, list):
            redacted_rows.append([
                _redact_artifact_value(cell, columns[index] if index < len(columns) else "")
                for index, cell in enumerate(row)
            ])
        elif isinstance(row, dict):
            redacted_rows.append(_redact_artifact_value(row))
        else:
            redacted_rows.append(_redact_artifact_value(row))
    return redacted_rows


def _safe_event_payload(event: AgentRuntimeEvent) -> dict[str, Any]:
    data = _redact_runtime_event_value(event.model_dump())
    if event.response is not None:
        resp_data = _redact_runtime_event_value(event.response.model_dump())
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
    payload = _parse_json(_model_optional_str(r, "payload_json")) or {}
    return {
        "id": _model_str(r, "id"),
        "run_id": _model_str(r, "run_id"),
        "semantic_id": _model_str(r, "semantic_id"),
        "type": _model_str(r, "type"),
        "title": _model_str(r, "title"),
        "produced_by_step": _model_str(r, "produced_by_step"),
        "depends_on": (_parse_json(_model_optional_str(r, "depends_on_json")) or {}).get("depends_on", []),
        "payload": _safe_artifact_payload(payload),
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
