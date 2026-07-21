"""Structured, secret-safe security audit records."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from engine.models import SecurityAuditRecord, utcnow


AuditOutcome = Literal["requested", "allowed", "denied", "cancelled", "succeeded", "failed"]
AUDIT_RETENTION_DAYS = 90
AUDIT_MAX_RECORDS = 20_000
AUDIT_DIAGNOSTIC_WINDOW_DAYS = 7
AUDIT_DIAGNOSTIC_MAX_RECORDS = 500
_SECRET_KEYS = frozenset({
    "password", "secret", "api_key", "apiKey", "token", "private_key",
    "passphrase", "credential", "credential_value",
})
_NORMALIZED_SECRET_KEYS = frozenset(item.lower() for item in _SECRET_KEYS)
_RESULT_KEYS = frozenset({"rows", "previewrows", "preview_rows", "series", "results"})


class SecurityAuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        action: str,
        outcome: AuditOutcome,
        resource_type: str,
        resource_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        actor_type: str = "local_user",
        actor_id: str | None = None,
        correlation_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> SecurityAuditRecord:
        sanitized = _sanitize(details or {})
        record = SecurityAuditRecord(
            id=f"audit_{uuid4().hex}",
            action=action,
            outcome=outcome,
            actor_type=actor_type,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            session_id=session_id,
            run_id=run_id,
            correlation_id=correlation_id or f"audit_correlation_{uuid4().hex}",
            details_json=json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        )
        self.session.add(record)
        return record

    def enforce_retention(
        self,
        *,
        retention_days: int = AUDIT_RETENTION_DAYS,
        max_records: int = AUDIT_MAX_RECORDS,
    ) -> int:
        """Bound the local audit store by age and count.

        Callers own the transaction so pruning can be committed atomically at
        startup or alongside an explicit audit lifecycle operation.
        """
        if retention_days < 1 or max_records < 1:
            raise ValueError("Audit retention bounds must be positive")
        cutoff = utcnow() - timedelta(days=retention_days)
        expired_result = self.session.execute(
            delete(SecurityAuditRecord).where(SecurityAuditRecord.created_at < cutoff)
        )
        expired = int(getattr(expired_result, "rowcount", 0) or 0)
        overflow_ids = list(
            self.session.execute(
                select(SecurityAuditRecord.id)
                .order_by(SecurityAuditRecord.created_at.desc(), SecurityAuditRecord.id.desc())
                .offset(max_records)
            ).scalars()
        )
        if overflow_ids:
            self.session.execute(
                delete(SecurityAuditRecord).where(SecurityAuditRecord.id.in_(overflow_ids))
            )
        return int(expired) + len(overflow_ids)

    def diagnostic_export(
        self,
        *,
        window_days: int = AUDIT_DIAGNOSTIC_WINDOW_DAYS,
        limit: int = AUDIT_DIAGNOSTIC_MAX_RECORDS,
    ) -> list[dict[str, Any]]:
        if not 1 <= window_days <= AUDIT_RETENTION_DAYS:
            raise ValueError("Audit export window is outside the retention policy")
        if not 1 <= limit <= AUDIT_DIAGNOSTIC_MAX_RECORDS:
            raise ValueError("Audit export limit is outside the diagnostic policy")
        cutoff = utcnow() - timedelta(days=window_days)
        records = self.session.execute(
            select(SecurityAuditRecord)
            .where(SecurityAuditRecord.created_at >= cutoff)
            .order_by(SecurityAuditRecord.created_at.desc(), SecurityAuditRecord.id.desc())
            .limit(limit)
        ).scalars()
        return [_export_record(record) for record in records]

    def clear(self) -> int:
        deleted_result = self.session.execute(delete(SecurityAuditRecord))
        deleted = int(getattr(deleted_result, "rowcount", 0) or 0)
        self.record(
            action="security.audit.clear",
            outcome="succeeded",
            resource_type="security_audit",
            details={"deleted_count": int(deleted)},
        )
        return int(deleted)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).lower() in _NORMALIZED_SECRET_KEYS
                else "[OMITTED_RESULT_DATA]"
                if str(key).lower() in _RESULT_KEYS
                else _sanitize(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(type(value).__name__)


def _export_record(record: SecurityAuditRecord) -> dict[str, Any]:
    try:
        details = json.loads(str(record.details_json or "{}"))
    except json.JSONDecodeError:
        details = {}
    return {
        "id": str(record.id),
        "action": str(record.action),
        "outcome": str(record.outcome),
        "actorType": str(record.actor_type),
        "resourceType": str(record.resource_type),
        "resourceId": str(record.resource_id) if record.resource_id else None,
        "sessionId": str(record.session_id) if record.session_id else None,
        "runId": str(record.run_id) if record.run_id else None,
        "correlationId": str(record.correlation_id),
        "details": _sanitize(details),
        "createdAt": record.created_at.isoformat(),
    }
