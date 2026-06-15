"""Tests for Spec 07 — DB Initialization Lifecycle."""
from __future__ import annotations

import importlib
import os
import sqlite3
import sys
from pathlib import Path

from engine.db import configure_sqlite_pragmas, DATABASE_URL


class TestConfigureSqlitePragmas:
    def test_noop_for_non_sqlite_url(self, tmp_path: Path) -> None:
        """Non-SQLite URLs must not create files or raise."""
        configure_sqlite_pragmas("postgresql://user:pass@localhost/test")
        assert not any(tmp_path.iterdir())

    def test_applies_wal_and_busy_timeout(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        url = f"sqlite:///{db_path}"
        configure_sqlite_pragmas(url)

        conn = sqlite3.connect(str(db_path))
        try:
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert journal.lower() == "wal"
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert busy > 0
        finally:
            conn.close()

    def test_idempotent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        url = f"sqlite:///{db_path}"
        configure_sqlite_pragmas(url)
        configure_sqlite_pragmas(url)
        assert db_path.exists()

    def test_import_db_does_not_create_file(self, tmp_path: Path, monkeypatch) -> None:
        """Importing engine.db with a temp DATABOX_DATABASE_URL must not create the file."""
        db_path = tmp_path / "import_test.db"
        monkeypatch.setenv("DATABOX_DATABASE_URL", f"sqlite:///{db_path}")
        # Remove cached module so it re-imports with the new env var
        mod_name = "engine.db"
        saved = sys.modules.pop(mod_name, None)
        try:
            importlib.import_module(mod_name)
            assert not db_path.exists(), "Import should not create the DB file"
        finally:
            if saved is not None:
                sys.modules[mod_name] = saved
            else:
                sys.modules.pop(mod_name, None)
