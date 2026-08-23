from __future__ import annotations

import logging
from typing import cast

from engine.app.safe_errors import (
    FixedErrorCode,
    SafeLogOperation,
    fixed_error_detail,
    fixed_error_message,
    log_extension_diagnostic,
    log_extension_exception,
    log_unexpected_exception,
)


def test_public_error_uses_only_fixed_catalog_entries() -> None:
    detail = fixed_error_detail(FixedErrorCode.CONSOLE_EXECUTION_ERROR)

    assert detail == {
        "code": "CONSOLE_EXECUTION_ERROR",
        "message": "The SQL Console request could not be completed.",
    }
    assert fixed_error_message(FixedErrorCode.SQL_EMPTY) == "SQL cannot be empty."


def test_every_fixed_error_code_has_a_nonempty_catalog_message() -> None:
    details = [fixed_error_detail(code) for code in FixedErrorCode]

    assert {detail["code"] for detail in details} == {code.value for code in FixedErrorCode}
    assert all(detail["message"].strip() for detail in details)


def test_public_error_unknown_value_falls_back_without_rendering_input() -> None:
    sentinel = "public-error-secret-sentinel"

    detail = fixed_error_detail(cast(FixedErrorCode, f"caller-code-{sentinel}"))

    assert detail == {
        "code": "INTERNAL_ERROR",
        "message": "The request could not be completed.",
    }
    assert sentinel not in repr(detail)


def test_safe_error_helpers_never_render_arbitrary_exception_or_operation_text(caplog) -> None:
    sentinel = "unstructured-exception-secret-sentinel"
    logger = logging.Logger("test.safe_errors_boundary")
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    logger.addHandler(caplog.handler)
    try:
        detail = fixed_error_detail(FixedErrorCode.DATASOURCE_POOL_RELEASE_FAILED)
        log_unexpected_exception(
            logger,
            operation=cast(SafeLogOperation, f"caller-operation-{sentinel}"),
            exc=RuntimeError(f"driver password={sentinel}"),
        )
    finally:
        logger.removeHandler(caplog.handler)

    assert detail == {
        "code": "DATASOURCE_POOL_RELEASE_FAILED",
        "message": "Datasource connection pool could not be released.",
    }
    assert sentinel not in caplog.text
    assert "unexpected_internal_error" in caplog.text
    assert "RuntimeError" in caplog.text


def test_extension_diagnostic_logs_only_namespaced_code_and_opaque_fingerprint(caplog) -> None:
    sentinel = "dlc-sql-secret-sentinel"
    logger = logging.Logger("test.extension_safe_log")
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    logger.addHandler(caplog.handler)
    try:
        log_extension_diagnostic(
            logger,
            operation="dbfox.data.sql_guardrail_parse",
            subject=f"SELECT '{sentinel}'",
            subject_type="sql",
        )
        log_extension_diagnostic(
            logger,
            operation=f"invalid-{sentinel}",
            subject=sentinel,
            subject_type="exception",
        )
        log_extension_exception(
            logger,
            operation="dbfox.data.sql_guardrail_parse",
            exc=RuntimeError(sentinel),
            fingerprint_subject=sentinel,
        )
    finally:
        logger.removeHandler(caplog.handler)

    assert "dbfox.data.sql_guardrail_parse" in caplog.text
    assert "extension.unexpected.operation" in caplog.text
    assert "RuntimeError" in caplog.text
    assert sentinel not in caplog.text
