from __future__ import annotations

import logging

from engine.app.errors import (
    log_unexpected_exception,
    public_error,
    public_message,
    safe_error_detail,
)


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


def test_safe_error_helpers_never_render_arbitrary_exception_text(caplog) -> None:
    sentinel = "unstructured-exception-secret-sentinel"
    logger = logging.getLogger("dbfox.tests.safe_errors")

    with caplog.at_level(logging.ERROR, logger="dbfox.tests.safe_errors"):
        detail = safe_error_detail("FIXED_ERROR", "A fixed public error message.")
        log_unexpected_exception(
            logger,
            operation="fixed_test_operation",
            exc=RuntimeError(f"driver password={sentinel}"),
        )

    assert detail == {"code": "FIXED_ERROR", "message": "A fixed public error message."}
    assert sentinel not in caplog.text
    assert "fixed_test_operation" in caplog.text
    assert "RuntimeError" in caplog.text
