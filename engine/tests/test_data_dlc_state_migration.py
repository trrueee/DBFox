from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from engine.migrations.data_dlc_state import migrate_legacy_data_sources


def _legacy_source(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'metadata.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE data_sources (
                id TEXT PRIMARY KEY, project_id TEXT, name TEXT NOT NULL,
                db_type TEXT NOT NULL, host TEXT, port INTEGER,
                database_name TEXT NOT NULL, username TEXT,
                password_credential_id TEXT, connection_mode TEXT,
                is_read_only INTEGER, env TEXT, ssh_enabled INTEGER,
                ssh_host TEXT, ssh_port INTEGER, ssh_username TEXT,
                ssh_password_credential_id TEXT, ssh_pkey_path TEXT,
                ssh_key_passphrase_credential_id TEXT, ssl_enabled INTEGER,
                ssl_ca_path TEXT, ssl_cert_path TEXT, ssl_key_path TEXT,
                ssl_verify_identity INTEGER, connection_generation INTEGER,
                status TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """))
    return engine


def test_data_import_preserves_database_resource_ids_and_is_replay_safe(
    tmp_path: Path,
) -> None:
    engine = _legacy_source(tmp_path)
    with engine.begin() as source:
        source.execute(text("""
            INSERT INTO data_sources VALUES
            ('database-billing', 'data-project', 'Billing', 'mysql',
             'db.internal', 3306, 'billing', 'analyst', 'credential:billing',
             'direct', 1, 'prod', 0, NULL, 22, NULL, NULL, NULL, NULL, 0,
             NULL, NULL, NULL, 1, 4, 'active',
             '2026-08-01 00:00:00', '2026-08-01 00:00:00'),
            ('database-analytics', 'data-project', 'Analytics', 'postgresql',
             'analytics.internal', 5432, 'analytics', NULL, NULL, 'direct',
             0, 'dev', 0, NULL, 22, NULL, NULL, NULL, NULL, 0, NULL, NULL,
             NULL, 1, 2, 'active',
             '2026-08-02 00:00:00', '2026-08-02 00:00:00')
        """))
        target = tmp_path / "dlcs" / "data" / "dbfox.data"
        result = migrate_legacy_data_sources(source, data_path=target)
        replay = migrate_legacy_data_sources(source, data_path=target)

    assert (result.source_row_count, result.imported_profile_count,
            result.imported_database_count) == (2, 2, 2)
    assert (replay.imported_profile_count, replay.imported_database_count) == (0, 0)
    with sqlite3.connect(target / "state.sqlite3") as connection:
        resources = connection.execute(
            "SELECT id, database_name, display_name, catalog_revision "
            "FROM database_resources ORDER BY id"
        ).fetchall()
        profiles = connection.execute(
            "SELECT name, provider, host, connection_generation, "
            "password_credential_ref FROM connection_profiles ORDER BY name"
        ).fetchall()
    assert resources == [
        ("database-analytics", "analytics", "Analytics", 0),
        ("database-billing", "billing", "Billing", 0),
    ]
    assert profiles == [
        ("Analytics", "postgresql", "analytics.internal", 2, None),
        ("Billing", "mysql", "db.internal", 4, "credential:billing"),
    ]
    engine.dispose()


def test_data_import_rejects_conflicting_target_state(tmp_path: Path) -> None:
    engine = _legacy_source(tmp_path)
    target = tmp_path / "dlcs" / "data" / "dbfox.data"
    with engine.begin() as source:
        source.execute(text("""
            INSERT INTO data_sources VALUES (
             'database-conflict', 'conflict-project', 'Original', 'sqlite',
             NULL, NULL, 'C:/data/original.db', NULL, NULL, 'direct', 0,
             'dev', 0, NULL, 22, NULL, NULL, NULL, NULL, 0, NULL, NULL,
             NULL, 1, 1, 'active', '2026-08-01 00:00:00',
             '2026-08-01 00:00:00')
        """))
        migrate_legacy_data_sources(source, data_path=target)
        with sqlite3.connect(target / "state.sqlite3") as connection:
            connection.execute(
                "UPDATE database_resources SET display_name = 'Tampered' "
                "WHERE id = 'database-conflict'"
            )
            connection.commit()
        with pytest.raises(RuntimeError, match="conflicting row"):
            migrate_legacy_data_sources(source, data_path=target)
    engine.dispose()
