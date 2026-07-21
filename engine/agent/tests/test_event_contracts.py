import json
from datetime import timedelta

import pytest

from engine.agent.events import (
    RUNTIME_EVENT_CONTRACTS,
    RuntimeEventType,
    validate_runtime_event_payload,
)
from engine.models import SecurityAuditRecord, utcnow
from engine.security.audit import SecurityAuditService


def test_every_public_event_has_one_versioned_contract() -> None:
    assert set(RUNTIME_EVENT_CONTRACTS) == set(RuntimeEventType)
    assert all(contract.version == 1 for contract in RUNTIME_EVENT_CONTRACTS.values())


def test_public_events_reject_result_rows_and_chart_series() -> None:
    with pytest.raises(ValueError, match="result values"):
        validate_runtime_event_payload(
            RuntimeEventType.ARTIFACT_CREATED,
            {"artifact": {"payload": {"rows": [{"secret": "value"}]}}},
        )
    with pytest.raises(ValueError, match="result values"):
        validate_runtime_event_payload(
            RuntimeEventType.ARTIFACT_CREATED,
            {"artifact": {"payload": {"series": [{"value": 1}]}}},
        )


def test_security_audit_redacts_secret_values(db_session) -> None:
    record = SecurityAuditService(db_session).record(
        action="credential.update",
        outcome="succeeded",
        resource_type="datasource",
        resource_id="ds-1",
        details={
            "Password": "do-not-store",
            "nested": {"api_key": "also-secret"},
            "rows": [{"private": "cell-value"}],
            "generation": 2,
        },
    )
    db_session.commit()
    stored = db_session.get(SecurityAuditRecord, record.id)
    payload = json.loads(stored.details_json)
    assert payload == {
        "generation": 2,
        "nested": {"api_key": "[REDACTED]"},
        "Password": "[REDACTED]",
        "rows": "[OMITTED_RESULT_DATA]",
    }
    assert "do-not-store" not in stored.details_json
    assert "cell-value" not in stored.details_json


def test_security_audit_retention_is_bounded_by_age_and_count(db_session) -> None:
    service = SecurityAuditService(db_session)
    for index in range(4):
        record = service.record(
            action="test.event",
            outcome="succeeded",
            resource_type="test",
            resource_id=str(index),
        )
        record.created_at = utcnow() - timedelta(days=120 if index == 0 else index)
    db_session.flush()

    deleted = service.enforce_retention(retention_days=90, max_records=2)
    db_session.commit()

    records = db_session.query(SecurityAuditRecord).order_by(SecurityAuditRecord.created_at.desc()).all()
    assert deleted == 2
    assert [record.resource_id for record in records] == ["1", "2"]
