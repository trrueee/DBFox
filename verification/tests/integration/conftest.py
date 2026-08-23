"""Independent metadata fixtures for cross-boundary verification."""

from __future__ import annotations

from pathlib import Path
from shutil import copy2

import pytest
from sqlalchemy.orm import sessionmaker

from engine.db import build_metadata_engine
from verification.support.metadata import (
    create_migrated_metadata_engine,
    sqlite_metadata_url,
)


@pytest.fixture(scope="session")
def metadata_template_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    template = tmp_path_factory.mktemp("integration_metadata") / "metadata.db"
    engine = create_migrated_metadata_engine(template)
    engine.dispose()
    return template


@pytest.fixture
def db_session(tmp_path: Path, metadata_template_file: Path):
    database_path = tmp_path / "metadata.db"
    copy2(metadata_template_file, database_path)
    engine = build_metadata_engine(sqlite_metadata_url(database_path))
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()

__all__ = ["db_session", "metadata_template_file"]
