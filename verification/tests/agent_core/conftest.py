"""Standalone fixtures for Agent Core verification.

The suite owns only an Alembic-upgraded Core metadata database. Capability
DLCs and their state belong to the System/DLC suites, never this fixture graph.
"""
from __future__ import annotations

from pathlib import Path
from shutil import copy2

import pytest
from sqlalchemy.orm import sessionmaker

from engine.db import build_metadata_engine
from engine.resource import ResourceScopeRef
from verification.support.metadata import (
    create_migrated_metadata_engine,
    sqlite_metadata_url,
)


def _open_db_session(database_path: Path):
    engine = build_metadata_engine(sqlite_metadata_url(database_path))
    session = sessionmaker(bind=engine)()
    return session, engine


@pytest.fixture(scope="session")
def metadata_template_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    template = tmp_path_factory.mktemp("agent_core_metadata") / "metadata.db"
    engine = create_migrated_metadata_engine(template)
    engine.dispose()
    return template


@pytest.fixture
def db_session(tmp_path: Path, metadata_template_file: Path):
    database_path = tmp_path / "metadata.db"
    copy2(metadata_template_file, database_path)
    session, engine = _open_db_session(database_path)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def authorized_resource_ref() -> ResourceScopeRef:
    return ResourceScopeRef(kind="verification.resource", id="resource-1", version=1)


@pytest.fixture
def test_resource(authorized_resource_ref: ResourceScopeRef) -> ResourceScopeRef:
    return authorized_resource_ref

__all__ = [
    "authorized_resource_ref",
    "db_session",
    "metadata_template_file",
    "test_resource",
]
