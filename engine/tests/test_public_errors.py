from __future__ import annotations

import logging
from typing import cast

from engine.app.errors import public_error, public_message
from engine.app.safe_errors import (
    FixedErrorCode,
    SafeLogOperation,
    fixed_error_detail,
    log_unexpected_exception,
)


def test_public_error_uses_only_fixed_catalog_entries() -> None:
    detail = public_error(FixedErrorCode.CONSOLE_EXECUTION_ERROR)

    assert detail == {
        "code": "CONSOLE_EXECUTION_ERROR",
        "message": "The SQL Console request could not be completed.",
    }
    assert public_message(FixedErrorCode.SQL_EMPTY) == "SQL cannot be empty."


def test_public_error_unknown_value_falls_back_without_rendering_input() -> None:
    sentinel = "public-error-secret-sentinel"

    detail = public_error(cast(FixedErrorCode, f"caller-code-{sentinel}"))
    direct_detail = fixed_error_detail(cast(FixedErrorCode, f"caller-code-{sentinel}"))

    assert detail == direct_detail == {
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
