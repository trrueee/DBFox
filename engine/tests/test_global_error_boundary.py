from __future__ import annotations

import asyncio
import logging

from starlette.requests import Request

from engine.errors import DBFoxError
from engine.main import dbfox_error_handler, global_unhandled_exception_handler
from engine.security.credential_vault import CredentialVaultUnavailableError


SENTINEL = "provider-sentinel-not-a-redaction-pattern"


def _isolated_main_logger(caplog, monkeypatch, *, level: int) -> logging.Logger:
    import engine.main as main_module

    logger = logging.Logger("test.global_error_boundary")
    logger.setLevel(level)
    logger.propagate = False
    logger.addHandler(caplog.handler)
    monkeypatch.setattr(main_module, "logger", logger)
    return logger


def test_global_exception_handler_logs_only_error_type_and_request_identity(
    caplog,
    monkeypatch,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/sentinel-boundary",
            "headers": [],
        }
    )
    logger = _isolated_main_logger(caplog, monkeypatch, level=logging.ERROR)
    try:
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
    finally:
        logger.removeHandler(caplog.handler)


def test_dbfox_error_handler_never_echoes_or_logs_an_untrusted_message(
    caplog,
    monkeypatch,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/dbfox-error-boundary",
            "headers": [],
        }
    )
    logger = _isolated_main_logger(caplog, monkeypatch, level=logging.WARNING)
    try:
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
    finally:
        logger.removeHandler(caplog.handler)


def test_dbfox_error_handler_preserves_the_safe_vault_unavailable_code(
    caplog,
    monkeypatch,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/credentials",
            "headers": [],
        }
    )
    logger = _isolated_main_logger(caplog, monkeypatch, level=logging.WARNING)
    try:
        response = asyncio.run(dbfox_error_handler(request, CredentialVaultUnavailableError()))

        payload = response.body.decode()
        assert response.status_code == 400
        assert "CREDENTIAL_VAULT_UNAVAILABLE" in payload
        assert "CREDENTIAL_VAULT_UNAVAILABLE" in caplog.text
    finally:
        logger.removeHandler(caplog.handler)
