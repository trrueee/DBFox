from __future__ import annotations

from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from engine.db import (
    build_alembic_config,
    build_metadata_engine,
    initialize_metadata_database,
    run_alembic_upgrade,
    verify_metadata_database,
)
from engine.security.runtime_reset import FOUNDATION_RUNTIME_VERSION


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _head(url: str) -> str:
    return ScriptDirectory.from_config(build_alembic_config(url)).get_current_head()


def test_agent_write_trace_path_stays_inside_private_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import engine.db as db_module

    monkeypatch.setattr(db_module, "private_runtime_dir", lambda name: tmp_path / name)

    path = db_module._agent_write_trace_path("20260712_010203")

    assert path == tmp_path / "diagnostics" / "db_write_trace_20260712_010203.jsonl"
    assert ".agent_eval" not in path.parts


def test_agent_write_trace_error_diagnostic_never_contains_exception_text() -> None:
    import engine.db as db_module

    sentinel = "database password=must-not-be-persisted"
    diagnostic = db_module._trace_error_diagnostic(RuntimeError(sentinel))

    assert diagnostic["error_type"] == "RuntimeError"
    assert diagnostic["error_fingerprint"]
    assert sentinel not in str(diagnostic)


def test_run_alembic_upgrade_creates_and_verifies_a_fresh_metadata_database(tmp_path: Path) -> None:
    metadata_url = _sqlite_url(tmp_path / "metadata.db")

    run_alembic_upgrade(metadata_url)
    verify_metadata_database(metadata_url)

    engine = build_metadata_engine(metadata_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == _head(
                metadata_url
            )
    finally:
        engine.dispose()


def test_run_alembic_upgrade_propagates_migration_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import alembic.command

    metadata_url = _sqlite_url(tmp_path / "metadata.db")

    def fail_upgrade(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("forced migration failure")

    monkeypatch.setattr(alembic.command, "upgrade", fail_upgrade)
    with pytest.raises(RuntimeError, match="forced migration failure"):
        run_alembic_upgrade(metadata_url)


def test_unversioned_partial_metadata_schema_is_not_inferred_or_stamped(tmp_path: Path) -> None:
    metadata_url = _sqlite_url(tmp_path / "metadata.db")
    engine = create_engine(metadata_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE data_sources (id TEXT PRIMARY KEY)"))
        with pytest.raises(Exception):
            run_alembic_upgrade(metadata_url)
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'alembic_version'"
                )
            ).scalar_one() == 0
    finally:
        engine.dispose()


def test_initialize_metadata_database_runs_reset_inside_the_shared_runtime_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import engine.db as db_module
    import engine.security.runtime_reset as runtime_reset

    runtime_root = tmp_path / "runtime"
    metadata_path = runtime_root / "data" / "dbfox_local.db"
    metadata_path.parent.mkdir(parents=True)
    metadata_url = _sqlite_url(metadata_path)
    project_root = tmp_path / "project"
    legacy_project_runtime = project_root / ".dbfox_runtime"
    legacy_project_token = legacy_project_runtime / "auth" / ".local_token"
    legacy_project_token.parent.mkdir(parents=True)
    legacy_project_token.write_text("must remain for custom DB URL", encoding="utf-8")

    monkeypatch.setattr(db_module, "DATABASE_URL", metadata_url)
    monkeypatch.setattr(db_module, "DB_PATH", metadata_path)
    monkeypatch.setattr(db_module, "_env_db_url", "test-isolated")
    monkeypatch.setattr(db_module, "private_runtime_root", lambda: runtime_root)
    monkeypatch.setattr(runtime_reset, "PROJECT_DIR", project_root)

    initialize_metadata_database()

    engine = build_metadata_engine(metadata_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT runtime_version FROM foundation_runtime_state WHERE id = 1")
            ).scalar_one() == FOUNDATION_RUNTIME_VERSION
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == _head(
                metadata_url
            )
    finally:
        engine.dispose()
    assert legacy_project_token.read_text(encoding="utf-8") == "must remain for custom DB URL"


def test_initializer_retires_only_the_known_source_mode_artifact_family(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import engine.db as db_module
    import engine.security.runtime_reset as runtime_reset

    runtime_root = tmp_path / "runtime"
    metadata_path = runtime_root / "data" / "dbfox_local.db"
    metadata_path.parent.mkdir(parents=True)
    metadata_url = _sqlite_url(metadata_path)
    legacy_root = tmp_path / "legacy-source"
    legacy_root.mkdir()
    legacy_metadata = legacy_root / "dbfox_local.db"
    legacy_checkpoint = legacy_root / "dbfox_agent_core_checkpoints.sqlite"
    legacy_metadata.write_bytes(b"legacy metadata")
    legacy_checkpoint.write_bytes(b"legacy checkpoint")
    unrelated = legacy_root / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")
    project_root = tmp_path / "project"
    legacy_project_runtime = project_root / ".dbfox_runtime"
    legacy_project_token = legacy_project_runtime / "auth" / ".local_token"
    legacy_project_token.parent.mkdir(parents=True)
    legacy_project_token.write_text("legacy token", encoding="utf-8")
    project_file = project_root / "keep.txt"
    project_file.write_text("keep", encoding="utf-8")

    monkeypatch.setattr(db_module, "DATABASE_URL", metadata_url)
    monkeypatch.setattr(db_module, "DB_PATH", metadata_path)
    monkeypatch.setattr(db_module, "_env_db_url", "")
    monkeypatch.setattr(db_module, "private_runtime_root", lambda: runtime_root)
    monkeypatch.setattr(db_module, "LEGACY_SOURCE_METADATA_PATH", legacy_metadata)
    monkeypatch.setattr(db_module, "LEGACY_SOURCE_RUNTIME_ROOT", legacy_root)
    monkeypatch.setattr(runtime_reset, "PROJECT_DIR", project_root)

    initialize_metadata_database()

    assert not legacy_metadata.exists()
    assert not legacy_checkpoint.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert not legacy_project_runtime.exists()
    assert project_file.read_text(encoding="utf-8") == "keep"
