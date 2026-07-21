"""Alembic-backed metadata-database helpers for tests.

Production metadata schema is owned exclusively by Alembic.  Test fixtures
must exercise that same contract rather than creating ORM tables directly.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

from engine.db import build_metadata_engine, run_alembic_upgrade


def sqlite_metadata_url(database_path: Path) -> str:
    """Return the SQLite URL for one explicit, file-backed test database."""
    return f"sqlite:///{database_path.resolve().as_posix()}"


def create_migrated_metadata_engine(database_path: Path) -> Engine:
    """Upgrade ``database_path`` to Alembic head and return its ORM engine.

    A file-backed database is deliberate: it exercises the same migration and
    SQLite connection behavior used by the application, including FTS objects
    and per-connection foreign-key enforcement.
    """
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = sqlite_metadata_url(database_path)
    run_alembic_upgrade(database_url)
    return build_metadata_engine(database_url)
