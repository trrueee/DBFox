"""Shared pytest fixtures for DBFox engine tests.

Fixture lifecycle (fastest → slowest, ordered by scope):

* ``db_session``          function  isolated copy of one migrated template
* template databases      session   built once, then copied per consumer

Templates are copied only after their creating connection is closed.  Tests
keep file-level isolation without repeating migrations or the large seed SQL.
"""
from pathlib import Path
from shutil import copy2

import pytest
from sqlalchemy.orm import sessionmaker
from engine.db import build_metadata_engine
from verification.support.metadata import (
    create_migrated_metadata_engine,
    sqlite_metadata_url,
)

def _open_db_session(database_path: Path):
    """Open one isolated copy of the migrated metadata template."""
    engine = build_metadata_engine(sqlite_metadata_url(database_path))
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    return session, engine


@pytest.fixture(scope="session")
def metadata_template_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    template = tmp_path_factory.mktemp("metadata_template") / "metadata.db"
    engine = create_migrated_metadata_engine(template)
    engine.dispose()
    return template


@pytest.fixture
def db_session(tmp_path: Path, metadata_template_file: Path):
    """Function-scoped metadata session backed by an isolated template copy."""
    database_path = tmp_path / "metadata.db"
    copy2(metadata_template_file, database_path)
    session, engine = _open_db_session(database_path)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(name="client")
def api_client_fixture(db_session):
    """Authenticated FastAPI client with dependency overrides restored exactly."""
    from fastapi.testclient import TestClient

    from engine.db import get_db
    from engine.main import LOCAL_SECURE_TOKEN, app

    previous_overrides = dict(app.dependency_overrides)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(
            app,
            headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


@pytest.fixture(scope="module")
def db_session_module(
    tmp_path_factory: pytest.TempPathFactory,
    metadata_template_file: Path,
):
    """Module-scoped file-backed Alembic-upgraded SQLite session.

    Use in test classes that only perform read-only catalog operations
    and do not modify tables within the same module.
    """
    database_path = tmp_path_factory.mktemp("metadata_module") / "metadata.db"
    copy2(metadata_template_file, database_path)
    session, engine = _open_db_session(database_path)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()

