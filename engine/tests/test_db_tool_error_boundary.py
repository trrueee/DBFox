from __future__ import annotations

import logging

import pytest

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
