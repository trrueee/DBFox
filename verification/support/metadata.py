"""Alembic-backed metadata helpers shared by verification suites."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

from engine.db import build_metadata_engine, run_alembic_upgrade


def sqlite_metadata_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.resolve().as_posix()}"


def create_migrated_metadata_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = sqlite_metadata_url(database_path)
    run_alembic_upgrade(database_url)
    return build_metadata_engine(database_url)
