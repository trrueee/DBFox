from __future__ import annotations

from engine.diagnostics.logs import redact_sensitive_text


def test_diagnostic_log_redaction_scrubs_pii_and_credentials() -> None:
    text = (
        "Authorization: Bearer diag-token "
        "X-Local-Token: local-token "
        "password='plain-secret' "
        "customer=alice@example.com "
        "phone=13800138000 "
        "card=4111111111111111"
    )

    redacted = redact_sensitive_text(text)

    assert "diag-token" not in redacted
    assert "local-token" not in redacted
    assert "plain-secret" not in redacted
    assert "alice@example.com" not in redacted
    assert "13800138000" not in redacted
    assert "4111111111111111" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_CARD]" in redacted
