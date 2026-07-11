from __future__ import annotations

import logging
import sqlite3

import pytest

import engine.tools.db.inspect as db_inspect_module
import engine.tools.db.search as db_search_module


SENTINEL = "db-tool-provider-secret-sentinel"


def _isolated_capture_logger(caplog: pytest.LogCaptureFixture, name: str) -> logging.Logger:
    logger = logging.Logger(name)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    logger.addHandler(caplog.handler)
    return logger


def test_db_search_fts_fallback_never_logs_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def failing_fts(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        raise RuntimeError(f"provider token={SENTINEL}")

    logger = _isolated_capture_logger(caplog, "test.db_search_error_boundary")
    try:
        monkeypatch.setattr(db_search_module, "logger", logger)
        monkeypatch.setattr(db_search_module, "_fts_search", failing_fts)
        monkeypatch.setattr(
            db_search_module,
            "_fallback_keyword_search",
            lambda *_args, **_kwargs: [],
        )

        result = db_search_module.db_search(object(), "datasource-boundary", "orders")
    finally:
        logger.removeHandler(caplog.handler)

    assert result["engine"] == "keyword_fallback"
    assert SENTINEL not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "db_search_fts_fallback" in caplog.text


def test_db_inspect_sqlite_fallback_never_logs_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingConnection:
        def execute(self, _sql: str) -> object:
            raise sqlite3.OperationalError(f"driver password={SENTINEL}")

    logger = _isolated_capture_logger(caplog, "test.db_inspect_error_boundary")
    try:
        monkeypatch.setattr(db_inspect_module, "logger", logger)
        assert db_inspect_module._sqlite_row_count(FailingConnection(), "orders") is None
    finally:
        logger.removeHandler(caplog.handler)

    assert SENTINEL not in caplog.text
    assert "OperationalError" in caplog.text
    assert "db_inspect_sqlite_row_count" in caplog.text
