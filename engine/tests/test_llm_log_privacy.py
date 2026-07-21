from __future__ import annotations

import pytest
from sqlalchemy import inspect

from engine.models import LLMLog


def test_llm_log_persists_only_non_sensitive_invocation_telemetry(db_session) -> None:
    prompt_hash = LLMLog.fingerprint_request(
        "schema contains customer email and password=secret",
        hmac_key=b"t" * 32,
    )
    log = LLMLog(
        request_type="text_to_sql",
        prompt_hash=prompt_hash,
        model_name="test-model",
        latency_ms=123,
        status="failed",
        error_code="LLM_INVOCATION_FAILED",
        prompt_version="v3",
        prompt_template_hash="a" * 64,
        model_temperature=0.2,
        max_tokens=512,
    )
    db_session.add(log)
    db_session.commit()

    saved = db_session.query(LLMLog).filter(LLMLog.id == log.id).one()

    assert saved.prompt_hash == prompt_hash
    assert saved.model_name == "test-model"
    assert saved.latency_ms == 123
    assert saved.status == "failed"
    assert saved.error_code == "LLM_INVOCATION_FAILED"
    assert saved.prompt_template_hash == "a" * 64

    columns = {column["name"] for column in inspect(db_session.bind).get_columns("llm_logs")}
    assert columns == {
        "id",
        "data_source_id",
        "request_type",
        "prompt_hash",
        "model_name",
        "latency_ms",
        "status",
        "error_code",
        "prompt_version",
        "prompt_template_hash",
        "model_temperature",
        "max_tokens",
        "created_at",
    }


@pytest.mark.parametrize(
    "legacy_field",
    ("prompt_text", "response_text", "error_message", "schema_validation_warnings"),
)
def test_llm_log_rejects_legacy_plaintext_fields(legacy_field: str) -> None:
    with pytest.raises(TypeError, match=rf"'{legacy_field}' is an invalid keyword argument"):
        LLMLog(request_type="text_to_sql", **{legacy_field: "sensitive value"})


def test_llm_log_rejects_non_fingerprint_request_hash_and_non_fixed_error_code() -> None:
    with pytest.raises(ValueError, match="hmac-sha256 request fingerprint"):
        LLMLog(request_type="text_to_sql", prompt_hash="customer email: secret@example.test")
    with pytest.raises(ValueError, match="fixed uppercase identifier"):
        LLMLog(request_type="text_to_sql", error_code="provider echoed secret")
