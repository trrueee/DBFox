"""Contract tests for the foundation v2 Alembic schema migration."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from engine.db import Base
from engine.models import FTS5_DDL, QUERY_HISTORY_FTS_DDL, FoundationRuntimeState


FOUNDATION_V2_REVISION = "3c5d7e9f1a2b"


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _alembic_config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "engine" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


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


def test_historical_create_all_then_stamp_2b_upgrades_without_duplicate_columns(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path / "historical-create-all.db")
    engine = create_engine(database_url)
    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as connection:
            connection.execute(text(FTS5_DDL))
            connection.execute(text(QUERY_HISTORY_FTS_DDL))
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES ('2b4c6d8e0f12')")
            )
    finally:
        engine.dispose()

    _upgrade(monkeypatch, database_url)
    engine = create_engine(database_url)
    try:
        _assert_final_contract(engine)
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


def test_foundation_runtime_state_model_is_a_singleton_marker() -> None:
    assert FoundationRuntimeState.__tablename__ == "foundation_runtime_state"
    assert {column.name for column in FoundationRuntimeState.__table__.columns} == {
        "id",
        "runtime_version",
        "reset_completed_at",
    }
