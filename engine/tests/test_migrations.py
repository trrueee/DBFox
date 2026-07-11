"""Contract tests for the foundation v2 Alembic schema migration."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from engine.db import Base
from engine.migrations.sqlite_mutex import SQLITE_MIGRATION_LOCKED, sqlite_migration_mutex
from engine.models import FoundationRuntimeState


FOUNDATION_V2_REVISION = "3c5d7e9f1a2b"
HISTORICAL_MODELS_REVISION = "918ea80d"
_QUERY_HISTORY_FTS_TRIGGERS = {
    "query_history_search_docs_ai",
    "query_history_search_docs_ad",
    "query_history_search_docs_au",
}
_OFFLINE_FAILURE = "DBFOX_ALEMBIC_OFFLINE_UNSUPPORTED"


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _alembic_config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "engine" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _create_real_historical_create_all_schema(database_url: str, tmp_path: Path) -> None:
    """Build the exact pre-v2 ORM shape from the committed baseline archive."""
    root = Path(__file__).resolve().parents[2]
    archive_path = tmp_path / f"models-{HISTORICAL_MODELS_REVISION}.tar"
    archive_root = tmp_path / "historical-models"
    with archive_path.open("wb") as archive_file:
        subprocess.run(
            ["git", "archive", "--format=tar", HISTORICAL_MODELS_REVISION, "engine/models.py"],
            cwd=root,
            check=True,
            stdout=archive_file,
        )
    with tarfile.open(archive_path) as archive:
        archive.extract(archive.getmember("engine/models.py"), archive_root, filter="data")

    historical_models = archive_root / "engine" / "models.py"
    script = '''
import importlib.util
import sys
import types
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base

models_path = Path(sys.argv[1])
database_url = sys.argv[2]

engine_package = types.ModuleType("engine")
engine_package.__path__ = [str(models_path.parent)]
sys.modules["engine"] = engine_package

db_module = types.ModuleType("engine.db")
db_module.Base = declarative_base()
sys.modules["engine.db"] = db_module

spec = importlib.util.spec_from_file_location("historical_engine_models", models_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

engine = create_engine(database_url)
try:
    module.Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO data_sources (
                id, name, db_type, host, port, database_name, username,
                ssh_enabled, ssh_port, ssl_enabled, ssl_verify_identity,
                connection_mode, is_read_only, env, status, created_at, updated_at
            ) VALUES (
                'historical-source', 'Historical source', 'sqlite', 'localhost', 0, ':memory:', '',
                0, 22, 0, 1, 'direct', 1, 'dev', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            INSERT INTO query_history (id, data_source_id, guardrail_result, created_at)
            VALUES ('historical-history', 'historical-source', 'allowed', CURRENT_TIMESTAMP)
        """))
        connection.execute(text("""
            INSERT INTO query_history_search_docs (
                history_id, datasource_id, search_text, updated_at
            ) VALUES (
                'historical-history', 'historical-source', 'historicalftsrebuildtoken', CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('2b4c6d8e0f12')"))
finally:
    engine.dispose()
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(historical_models), database_url],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _upgrade(monkeypatch, database_url: str, revision: str = "head") -> None:
    """Run Alembic against an isolated engine even before env.py is repaired."""
    import engine.db as db_module

    migration_engine = create_engine(database_url, connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_module, "DATABASE_URL", database_url)
    monkeypatch.setattr(db_module, "engine", migration_engine)
    try:
        command.upgrade(_alembic_config(database_url), revision)
    finally:
        migration_engine.dispose()


def _column_names(engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _assert_final_contract(engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    assert "foundation_runtime_state" in tables
    assert {column["name"] for column in inspector.get_columns("foundation_runtime_state")} == {
        "id",
        "runtime_version",
        "reset_completed_at",
    }
    assert any(
        "id" in str(check["sqltext"]).lower() and "1" in str(check["sqltext"])
        for check in inspector.get_check_constraints("foundation_runtime_state")
    )

    data_source_columns = _column_names(engine, "data_sources")
    assert {
        "password_credential_id",
        "ssh_password_credential_id",
        "ssh_key_passphrase_credential_id",
    } == {
        column
        for column in data_source_columns
        if "credential_id" in column
        or "ciphertext" in column
        or "nonce" in column
        or "key_version" in column
    }

    environment_columns = _column_names(engine, "database_environments")
    assert {
        "password_credential_id",
    } == {
        column
        for column in environment_columns
        if "credential_id" in column
        or "ciphertext" in column
        or "nonce" in column
        or "key_version" in column
    }

    assert {
        "llm_credential_id",
        "api_base",
        "model_name",
    }.issubset(_column_names(engine, "agent_runs"))

    data_source_fks = inspector.get_foreign_keys("data_sources")
    assert any(
        fk["constrained_columns"] == ["environment_id"]
        and fk["referred_table"] == "database_environments"
        and fk["options"].get("ondelete") == "SET NULL"
        for fk in data_source_fks
    )
    environment_fks = inspector.get_foreign_keys("database_environments")
    assert any(
        fk["constrained_columns"] == ["datasource_id"]
        and fk["referred_table"] == "data_sources"
        and fk["options"].get("ondelete") == "SET NULL"
        for fk in environment_fks
    )

    schema_column_fks = inspector.get_foreign_keys("schema_columns")
    assert any(
        fk["constrained_columns"] == ["table_id"]
        and fk["referred_table"] == "schema_tables"
        and fk["options"].get("ondelete") == "CASCADE"
        for fk in schema_column_fks
    )
    assert any(
        fk["constrained_columns"] == ["foreign_table_id"]
        and fk["referred_table"] == "schema_tables"
        and fk["options"].get("ondelete") == "SET NULL"
        for fk in schema_column_fks
    )

    assert any(
        fk["constrained_columns"] == ["session_id"]
        and fk["referred_table"] == "agent_sessions"
        and fk["options"].get("ondelete") == "CASCADE"
        for fk in inspector.get_foreign_keys("agent_approvals")
    )
    assert any(
        fk["constrained_columns"] == ["table_id"]
        and fk["referred_table"] == "schema_tables"
        and fk["options"].get("ondelete") == "CASCADE"
        for fk in inspector.get_foreign_keys("workspace_table_scopes")
    )
    assert any(
        fk["constrained_columns"] == ["foreign_column_id"]
        and fk["referred_table"] == "schema_columns"
        and fk["options"].get("ondelete") == "SET NULL"
        for fk in schema_column_fks
    )

    assert {"schema_search_fts", "query_history_fts"}.issubset(tables)


def test_fresh_upgrade_has_the_complete_foundation_v2_contract(monkeypatch, tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path / "fresh.db")
    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                FOUNDATION_V2_REVISION
            )
            assert connection.execute(text("SELECT COUNT(*) FROM foundation_runtime_state")).scalar_one() == 0
        _assert_final_contract(engine)
        command.check(_alembic_config(database_url))
    finally:
        engine.dispose()


def test_canonical_2b_upgrade_preserves_endpoint_metadata_and_removes_legacy_secrets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "canonical-2b.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO projects (id, name, description, status, created_at, updated_at)
                    VALUES ('project-1', 'Foundation migration project', NULL, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO data_sources (
                        id, project_id, name, db_type, host, port, database_name, username,
                        password_ciphertext, password_nonce, password_key_version,
                        ssh_enabled, ssh_port, ssl_enabled, ssl_verify_identity,
                        connection_mode, is_read_only, env, status, created_at, updated_at
                    ) VALUES (
                        'orphan-source', 'missing-project', 'Orphan endpoint', 'mysql', 'orphan.internal', 3306,
                        'warehouse', 'reader', 'legacy-ciphertext', 'legacy-nonce', 'v1',
                        0, 22, 0, 1, 'direct', 1, 'prod', 'active', CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO data_sources (
                        id, project_id, environment_id, name, db_type, host, port, database_name, username,
                        password_ciphertext, password_nonce, password_key_version,
                        ssh_enabled, ssh_port, ssl_enabled, ssl_verify_identity,
                        connection_mode, is_read_only, env, status, created_at, updated_at
                    ) VALUES (
                        'source-1', 'project-1', 'environment-1', 'Production', 'postgresql', 'db.internal', 5432,
                        'analytics', 'readonly', 'legacy-ciphertext', 'legacy-nonce', 'v1',
                        0, 22, 1, 1, 'direct', 1, 'prod', 'active', CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO schema_tables (
                        id, data_source_id, table_schema, table_name, created_at, updated_at
                    ) VALUES (
                        'orphan-table', 'missing-source', 'public', 'orphan_table', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO database_environments (
                        id, project_id, name, runtime, engine_type, engine_version, image,
                        container_name, host, port, database_name, username,
                        password_ciphertext, password_nonce, datasource_id, status,
                        created_at, updated_at
                    ) VALUES (
                        'environment-1', 'project-1', 'Production environment', 'docker', 'postgresql',
                        '16', 'postgres:16', 'dbfox-prod', 'db.internal', 5432, 'analytics',
                        'readonly', 'environment-ciphertext', 'environment-nonce', 'source-1',
                        'ready', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO schema_tables (
                        id, data_source_id, table_schema, table_name, created_at, updated_at
                    ) VALUES (
                        'table-1', 'source-1', 'public', 'orders', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO schema_columns (
                        id, table_id, column_name, is_nullable, is_primary_key, is_foreign_key,
                        created_at, updated_at
                    ) VALUES (
                        'column-1', 'table-1', 'id', 0, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO schema_columns (
                        id, table_id, column_name, is_nullable, is_primary_key, is_foreign_key,
                        foreign_table_id, foreign_column_id, created_at, updated_at
                    ) VALUES (
                        'column-2', 'table-1', 'parent_id', 1, 0, 1, 'table-1', 'column-1',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            migrated = connection.execute(
                text(
                    """
                    SELECT id, environment_id, host, port, database_name, username, password_credential_id
                    FROM data_sources WHERE id = 'source-1'
                    """
                )
            ).mappings().one()
        assert dict(migrated) == {
            "id": "source-1",
            "environment_id": "environment-1",
            "host": "db.internal",
            "port": 5432,
            "database_name": "analytics",
            "username": "readonly",
            "password_credential_id": None,
        }
        with engine.connect() as connection:
            orphan_endpoint = connection.execute(
                text(
                    """
                    SELECT id, project_id, host, port, database_name, username, password_credential_id
                    FROM data_sources WHERE id = 'orphan-source'
                    """
                )
            ).mappings().one()
            assert dict(orphan_endpoint) == {
                "id": "orphan-source",
                "project_id": None,
                "host": "orphan.internal",
                "port": 3306,
                "database_name": "warehouse",
                "username": "reader",
                "password_credential_id": None,
            }
            assert connection.execute(
                text("SELECT COUNT(*) FROM schema_tables WHERE id = 'orphan-table'")
            ).scalar_one() == 0
            environment = connection.execute(
                text(
                    """
                    SELECT datasource_id, host, port, database_name, username, password_credential_id
                    FROM database_environments WHERE id = 'environment-1'
                    """
                )
            ).mappings().one()
            assert dict(environment) == {
                "datasource_id": "source-1",
                "host": "db.internal",
                "port": 5432,
                "database_name": "analytics",
                "username": "readonly",
                "password_credential_id": None,
            }
            catalog_reference = connection.execute(
                text(
                    """
                    SELECT foreign_table_id, foreign_column_id
                    FROM schema_columns WHERE id = 'column-2'
                    """
                )
            ).mappings().one()
            assert dict(catalog_reference) == {
                "foreign_table_id": "table-1",
                "foreign_column_id": "column-1",
            }
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        _assert_final_contract(engine)
    finally:
        engine.dispose()


def test_v2_preflight_fails_before_mutating_a_2b_database_missing_fts_content(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "missing-fts-content.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE schema_search_docs"))
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="FTS content tables are missing: schema_search_docs"):
        _upgrade(monkeypatch, database_url)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "2b4c6d8e0f12"
            )
            assert "foundation_runtime_state" not in inspect(connection).get_table_names()
            data_source_columns = _column_names(engine, "data_sources")
            assert {
                "password_ciphertext",
                "password_nonce",
                "password_key_version",
            }.issubset(data_source_columns)
            assert "password_credential_id" not in data_source_columns
    finally:
        engine.dispose()


def test_v2_preflight_rejects_unrepairable_fk_before_mutating_a_2b_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "invalid-fk-preflight.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE legacy_invalid_parent (id INTEGER)"))
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_invalid_child (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER,
                        FOREIGN KEY (parent_id) REFERENCES legacy_invalid_parent(id)
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="cannot repair invalid foreign key configuration"):
        _upgrade(monkeypatch, database_url)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "2b4c6d8e0f12"
            )
            assert "foundation_runtime_state" not in inspect(connection).get_table_names()
            data_source_columns = _column_names(engine, "data_sources")
            assert "password_ciphertext" in data_source_columns
            assert "password_credential_id" not in data_source_columns
    finally:
        engine.dispose()


def test_v2_version_stamp_failure_rolls_back_schema_atomically(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "version-stamp-rollback.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    CREATE TRIGGER fail_foundation_v2_version_stamp
                    BEFORE UPDATE OF version_num ON alembic_version
                    WHEN NEW.version_num = '{FOUNDATION_V2_REVISION}'
                    BEGIN
                        SELECT RAISE(FAIL, 'forced foundation v2 version stamp failure');
                    END
                    """
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(IntegrityError, match="forced foundation v2 version stamp failure"):
        _upgrade(monkeypatch, database_url)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "2b4c6d8e0f12"
            )
            assert "foundation_runtime_state" not in inspect(connection).get_table_names()
            trigger_names = {
                row[0]
                for row in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
                )
            }
            assert "fail_foundation_v2_version_stamp" in trigger_names
            data_source_columns = {
                column["name"] for column in inspect(connection).get_columns("data_sources")
            }
            assert {
                "password_ciphertext",
                "password_nonce",
                "password_key_version",
            }.issubset(data_source_columns)
            assert "password_credential_id" not in data_source_columns
            environment_columns = {
                column["name"]
                for column in inspect(connection).get_columns("database_environments")
            }
            assert {
                "password_ciphertext",
                "password_nonce",
            }.issubset(environment_columns)
            assert "password_credential_id" not in environment_columns
    finally:
        engine.dispose()


def test_v2_post_stamp_fk_violation_rolls_back_before_commit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "post-stamp-fk-rollback.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE legacy_stamp_parent (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_stamp_child (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER NOT NULL,
                        FOREIGN KEY (parent_id) REFERENCES legacy_stamp_parent(id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    f"""
                    CREATE TRIGGER create_post_stamp_fk_violation
                    AFTER UPDATE OF version_num ON alembic_version
                    WHEN NEW.version_num = '{FOUNDATION_V2_REVISION}'
                    BEGIN
                        INSERT INTO legacy_stamp_child (id, parent_id) VALUES (1, 999);
                    END
                    """
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="DBFOX_ALEMBIC_SQLITE_FOREIGN_KEY_VIOLATIONS"):
        _upgrade(monkeypatch, database_url)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "2b4c6d8e0f12"
            )
            assert "foundation_runtime_state" not in inspect(connection).get_table_names()
            assert connection.execute(
                text("SELECT COUNT(*) FROM legacy_stamp_child")
            ).scalar_one() == 0
            trigger_names = {
                row[0]
                for row in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
                )
            }
            assert "create_post_stamp_fk_violation" in trigger_names
    finally:
        engine.dispose()


def test_v2_removes_ascii_case_variant_legacy_secret_columns(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "case-variant-legacy-secrets.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            for column_name in (
                "password_ciphertext",
                "password_nonce",
                "password_key_version",
                "ssh_password_ciphertext",
                "ssh_password_nonce",
                "ssh_pkey_passphrase_ciphertext",
                "ssh_pkey_passphrase_nonce",
            ):
                connection.execute(
                    text(
                        "ALTER TABLE data_sources RENAME COLUMN "
                        f"{column_name} TO {column_name.upper()}"
                    )
                )
            for column_name in ("password_ciphertext", "password_nonce"):
                connection.execute(
                    text(
                        "ALTER TABLE database_environments RENAME COLUMN "
                        f"{column_name} TO {column_name.upper()}"
                    )
                )
    finally:
        engine.dispose()

    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            legacy_data_source_columns = {
                "password_ciphertext",
                "password_nonce",
                "password_key_version",
                "ssh_password_ciphertext",
                "ssh_password_nonce",
                "ssh_pkey_passphrase_ciphertext",
                "ssh_pkey_passphrase_nonce",
            }
            data_source_columns = {
                column["name"].lower()
                for column in inspect(connection).get_columns("data_sources")
            }
            assert not legacy_data_source_columns & data_source_columns
            environment_columns = {
                column["name"].lower()
                for column in inspect(connection).get_columns("database_environments")
            }
            assert not {"password_ciphertext", "password_nonce", "password_key_version"} & environment_columns
    finally:
        engine.dispose()


def test_real_historical_create_all_then_stamp_2b_restores_fts_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "historical-create-all.db")
    _create_real_historical_create_all_schema(database_url, tmp_path)

    engine = create_engine(database_url)
    try:
        historical_tables = set(inspect(engine).get_table_names())
        assert not {"schema_search_fts", "query_history_fts"} & historical_tables
        with engine.connect() as connection:
            historical_triggers = {
                row[0]
                for row in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
                )
            }
        assert not _QUERY_HISTORY_FTS_TRIGGERS & historical_triggers
    finally:
        engine.dispose()

    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        _assert_final_contract(engine)
        with engine.connect() as connection:
            trigger_names = {
                row[0]
                for row in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
                )
            }
            assert _QUERY_HISTORY_FTS_TRIGGERS <= trigger_names
            connection.execute(text("SELECT search_text FROM schema_search_fts LIMIT 0"))
            connection.execute(text("SELECT search_text FROM query_history_fts LIMIT 0"))
            assert connection.execute(
                text(
                    """
                    SELECT COUNT(*) FROM query_history_fts
                        WHERE query_history_fts MATCH 'historicalftsrebuildtoken'
                    """
                )
            ).scalar_one() == 1
    finally:
        engine.dispose()


def test_online_migrations_honor_the_configured_temporary_url(monkeypatch, tmp_path: Path) -> None:
    import engine.db as db_module

    configured_url = _sqlite_url(tmp_path / "configured.db")
    decoy_url = _sqlite_url(tmp_path / "module-global.db")
    decoy_engine = create_engine(decoy_url, connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_module, "DATABASE_URL", decoy_url)
    monkeypatch.setattr(db_module, "engine", decoy_engine)

    try:
        command.upgrade(_alembic_config(configured_url), "2b4c6d8e0f12")
    finally:
        decoy_engine.dispose()

    configured_engine = create_engine(configured_url)
    decoy_engine = create_engine(decoy_url)
    try:
        with configured_engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "2b4c6d8e0f12"
            )
        with decoy_engine.connect() as connection:
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        configured_engine.dispose()
        decoy_engine.dispose()


def test_sqlite_migration_write_lock_blocks_snapshot_race(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-write-lock.db"
    database_url = _sqlite_url(database_path)
    setup_engine = create_engine(database_url)
    try:
        with setup_engine.begin() as connection:
            connection.execute(text("CREATE TABLE lock_probe (id INTEGER PRIMARY KEY)"))
    finally:
        setup_engine.dispose()

    migration_engine = create_engine(database_url, connect_args={"timeout": 0.1})
    writer_engine = create_engine(database_url, connect_args={"timeout": 0.1})
    try:
        with migration_engine.connect() as migration_connection:
            migration_connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            migration_connection.commit()
            migration_connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                snapshot_source = sqlite3.connect(database_path)
                snapshot = sqlite3.connect(":memory:")
                try:
                    snapshot_source.backup(snapshot)
                    assert snapshot.execute(
                        "SELECT name FROM sqlite_master WHERE name = 'lock_probe'"
                    ).fetchone() == ("lock_probe",)
                finally:
                    snapshot_source.close()
                    snapshot.close()
                with writer_engine.connect() as writer_connection:
                    with pytest.raises(OperationalError, match="database is locked"):
                        writer_connection.execute(text("INSERT INTO lock_probe (id) VALUES (1)"))
            finally:
                migration_connection.rollback()
    finally:
        migration_engine.dispose()
        writer_engine.dispose()


def test_cli_offline_upgrade_fails_closed_before_any_migration(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "offline.db"
    env = os.environ.copy()
    env["DBFOX_DATABASE_URL"] = _sqlite_url(database_path)

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert _OFFLINE_FAILURE in output
    assert "Running upgrade" not in output
    assert not database_path.exists()


def test_cli_v2_version_stamp_failure_restores_sqlite_file_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "cli-version-stamp-rollback.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    CREATE TRIGGER fail_cli_foundation_v2_version_stamp
                    BEFORE UPDATE OF version_num ON alembic_version
                    WHEN NEW.version_num = '{FOUNDATION_V2_REVISION}'
                    BEGIN
                        SELECT RAISE(FAIL, 'forced CLI foundation v2 version stamp failure');
                    END
                    """
                )
            )
    finally:
        engine.dispose()

    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["DBFOX_DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "forced CLI foundation v2 version stamp failure" in output

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "2b4c6d8e0f12"
            )
            assert "foundation_runtime_state" not in inspect(connection).get_table_names()
            data_source_columns = {
                column["name"] for column in inspect(connection).get_columns("data_sources")
            }
            assert "password_ciphertext" in data_source_columns
            assert "password_credential_id" not in data_source_columns
    finally:
        engine.dispose()


def test_cli_sqlite_migration_mutex_blocks_a_second_migration(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "cli-migration-mutex.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["DBFOX_DATABASE_URL"] = database_url
    env["DBFOX_ALEMBIC_SQLITE_MUTEX_TIMEOUT_SECONDS"] = "0.1"
    with sqlite_migration_mutex(database_url, timeout_seconds=0):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert SQLITE_MIGRATION_LOCKED in output

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "2b4c6d8e0f12"
            )
    finally:
        engine.dispose()


def test_v2_orphan_repair_converges_for_long_chains_and_mixed_composite_keys(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "orphan-repair.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_self_chain (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER NOT NULL,
                        FOREIGN KEY (parent_id) REFERENCES legacy_self_chain(id)
                    )
                    """
                )
            )
            chain_rows = [{"id": 1, "parent_id": 9_999}]
            chain_rows.extend({"id": value, "parent_id": value - 1} for value in range(2, 97))
            connection.execute(
                text("INSERT INTO legacy_self_chain (id, parent_id) VALUES (:id, :parent_id)"),
                chain_rows,
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_composite_parent (
                        key_a INTEGER NOT NULL,
                        key_b INTEGER NOT NULL,
                        PRIMARY KEY (key_a, key_b)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_composite_child (
                        id INTEGER PRIMARY KEY,
                        key_a INTEGER NOT NULL,
                        key_b INTEGER,
                        FOREIGN KEY (key_a, key_b)
                            REFERENCES legacy_composite_parent(key_a, key_b)
                    )
                    """
                )
            )
            connection.execute(
                text("INSERT INTO legacy_composite_child (id, key_a, key_b) VALUES (1, 7, 9)")
            )
    finally:
        engine.dispose()

    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM legacy_self_chain")).scalar_one() == 0
            assert connection.execute(
                text("SELECT key_a, key_b FROM legacy_composite_child WHERE id = 1")
            ).one() == (7, None)
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    finally:
        engine.dispose()


def test_v2_orphan_repair_preserves_valid_case_variant_foreign_keys(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "case-variant-foreign-keys.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE legacy_case_parent (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_case_nullable_child (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER,
                        FOREIGN KEY (parent_id) REFERENCES Legacy_Case_Parent(id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_case_required_child (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER NOT NULL,
                        FOREIGN KEY (parent_id) REFERENCES LEGACY_CASE_PARENT(id)
                    )
                    """
                )
            )
            connection.execute(text("INSERT INTO legacy_case_parent (id) VALUES (1)"))
            connection.execute(
                text("INSERT INTO legacy_case_nullable_child (id, parent_id) VALUES (1, 1)")
            )
            connection.execute(
                text("INSERT INTO legacy_case_required_child (id, parent_id) VALUES (1, 1)")
            )
    finally:
        engine.dispose()

    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT id, parent_id FROM legacy_case_nullable_child")
            ).one() == (1, 1)
            assert connection.execute(
                text("SELECT id, parent_id FROM legacy_case_required_child")
            ).one() == (1, 1)
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    finally:
        engine.dispose()


def test_v2_orphan_repair_distinguishes_unicode_sqlite_identifiers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "unicode-sqlite-identifiers.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE "ß" (id INTEGER PRIMARY KEY)'))
            connection.execute(text("CREATE TABLE ss (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_unicode_sharp_s_child (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER NOT NULL,
                        FOREIGN KEY (parent_id) REFERENCES "ß"(id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_unicode_ss_child (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER NOT NULL,
                        FOREIGN KEY (parent_id) REFERENCES ss(id)
                    )
                    """
                )
            )
            connection.execute(text('INSERT INTO "ß" (id) VALUES (1)'))
            connection.execute(text("INSERT INTO ss (id) VALUES (2)"))
            connection.execute(
                text("INSERT INTO legacy_unicode_sharp_s_child (id, parent_id) VALUES (1, 1)")
            )
            connection.execute(
                text("INSERT INTO legacy_unicode_ss_child (id, parent_id) VALUES (1, 2)")
            )
    finally:
        engine.dispose()

    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT parent_id FROM legacy_unicode_sharp_s_child")
            ).scalar_one() == 1
            assert connection.execute(
                text("SELECT parent_id FROM legacy_unicode_ss_child")
            ).scalar_one() == 2
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    finally:
        engine.dispose()


def test_v2_orphan_repair_handles_missing_parent_tables(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "missing-parent-orphans.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_missing_parent_nullable_child (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER,
                        FOREIGN KEY (parent_id) REFERENCES Legacy_Missing_Parent(id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_missing_parent_required_child (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER NOT NULL,
                        FOREIGN KEY (parent_id) REFERENCES Legacy_Missing_Parent(id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "INSERT INTO legacy_missing_parent_nullable_child (id, parent_id) VALUES (1, 999)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO legacy_missing_parent_required_child (id, parent_id) VALUES (1, 999)"
                )
            )
    finally:
        engine.dispose()

    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT id, parent_id FROM legacy_missing_parent_nullable_child")
            ).one() == (1, None)
            assert connection.execute(
                text("SELECT COUNT(*) FROM legacy_missing_parent_required_child")
            ).scalar_one() == 0
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    finally:
        engine.dispose()


def test_v2_orphan_repair_preserves_valid_rows_with_nullable_composite_primary_keys(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "nullable-composite-primary-key.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE legacy_rowid_parent (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_rowid_child (
                        key_a INTEGER,
                        key_b INTEGER,
                        parent_id INTEGER,
                        PRIMARY KEY (key_a, key_b),
                        FOREIGN KEY (parent_id) REFERENCES legacy_rowid_parent(id)
                    )
                    """
                )
            )
            connection.execute(text("INSERT INTO legacy_rowid_parent (id) VALUES (1)"))
            connection.execute(
                text(
                    "INSERT INTO legacy_rowid_child (key_a, key_b, parent_id) VALUES (NULL, 1, 999)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO legacy_rowid_child (key_a, key_b, parent_id) VALUES (NULL, 1, 1)"
                )
            )
    finally:
        engine.dispose()

    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT parent_id FROM legacy_rowid_child ORDER BY parent_id")
            ).scalars().all() == [None, 1]
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    finally:
        engine.dispose()


def test_v2_orphan_repair_deletes_nullable_fk_blocked_by_check_constraint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "checked-nullable-orphan.db")
    _upgrade(monkeypatch, database_url, "2b4c6d8e0f12")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE legacy_checked_parent (id INTEGER PRIMARY KEY)")
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE legacy_checked_child (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER,
                        CHECK (parent_id IS NOT NULL),
                        FOREIGN KEY (parent_id) REFERENCES legacy_checked_parent(id)
                    )
                    """
                )
            )
            connection.execute(
                text("INSERT INTO legacy_checked_child (id, parent_id) VALUES (1, 999)")
            )
    finally:
        engine.dispose()

    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT COUNT(*) FROM legacy_checked_child")
            ).scalar_one() == 0
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    finally:
        engine.dispose()


def test_foundation_runtime_state_model_is_a_singleton_marker() -> None:
    assert FoundationRuntimeState.__tablename__ == "foundation_runtime_state"
    assert {column.name for column in FoundationRuntimeState.__table__.columns} == {
        "id",
        "runtime_version",
        "reset_completed_at",
    }
