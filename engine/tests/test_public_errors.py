from __future__ import annotations

from engine.app.errors import public_error, public_message


def test_public_error_sanitizes_exception_message() -> None:
    detail = public_error(
        "BROKEN",
        RuntimeError("database failed: mysql://root:secret@1.2.3.4/prod password=secret"),
    )

    assert detail["code"] == "BROKEN"
    assert "[REDACTED]" in detail["message"]
    assert "secret" not in detail["message"]
    assert "mysql://root" not in detail["message"]


def test_public_message_sanitizes_plain_string() -> None:
    message = public_message("token=abc123 password=hunter2")

    assert "[REDACTED]" in message
    assert "hunter2" not in message


def test_public_message_sanitizes_raw_api_key() -> None:
    message = public_message("provider rejected sk-live-secret1234567890")

    assert "sk-live-secret1234567890" not in message
    assert "[REDACTED]" in message
