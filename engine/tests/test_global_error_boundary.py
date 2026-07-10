from __future__ import annotations

import asyncio
import logging

from starlette.requests import Request

from engine.errors import DBFoxError
from engine.main import dbfox_error_handler, global_unhandled_exception_handler
from engine.security.credential_vault import CredentialVaultUnavailableError


SENTINEL = "provider-sentinel-not-a-redaction-pattern"


def test_global_exception_handler_logs_only_error_type_and_request_identity(
    caplog,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/sentinel-boundary",
            "headers": [],
        }
    )
    caplog.set_level(logging.ERROR, logger="dbfox.main")

    try:
        raise RuntimeError(SENTINEL)
    except RuntimeError as exc:
        response = asyncio.run(global_unhandled_exception_handler(request, exc))

    payload = response.body.decode()
    assert response.status_code == 500
    assert "INTERNAL_ERROR" in payload
    assert SENTINEL not in payload
    assert SENTINEL not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "POST /api/v1/sentinel-boundary" in caplog.text


def test_dbfox_error_handler_never_echoes_or_logs_an_untrusted_message(
    caplog,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/dbfox-error-boundary",
            "headers": [],
        }
    )
    caplog.set_level(logging.WARNING, logger="dbfox.main")

    error = DBFoxError(SENTINEL, code="SAFE_TEST_ERROR")
    error.checks = [{"message": SENTINEL}]
    response = asyncio.run(dbfox_error_handler(request, error))

    payload = response.body.decode()
    assert response.status_code == 400
    assert "DBFOX_ERROR" in payload
    assert SENTINEL not in payload
    assert SENTINEL not in caplog.text
    assert "DBFoxError" in caplog.text
    assert "DBFOX_ERROR" in caplog.text
    assert "POST /api/v1/dbfox-error-boundary" in caplog.text


def test_dbfox_error_handler_preserves_the_safe_vault_unavailable_code(
    caplog,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/credentials",
            "headers": [],
        }
    )
    caplog.set_level(logging.WARNING, logger="dbfox.main")

    response = asyncio.run(dbfox_error_handler(request, CredentialVaultUnavailableError()))

    payload = response.body.decode()
    assert response.status_code == 400
    assert "CREDENTIAL_VAULT_UNAVAILABLE" in payload
    assert "CREDENTIAL_VAULT_UNAVAILABLE" in caplog.text
