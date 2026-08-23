"""One-way staging import from legacy DataSource rows into dbfox.data state.

This importer does not cut reads/writes over and does not delete Core rows.
Stage F owns that cutover after SQL/catalog/backup consumers use DatabaseResource
identity. Keeping the importer replay-safe lets release migration stage target
state without creating a second write path.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from engine.models import DEFAULT_PROJECT_ID, DataSource


@dataclass(frozen=True)
class DataDlcImportResult:
    source_row_count: int
    imported_profile_count: int
    imported_database_count: int


def _profile_id(datasource_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"dbfox.data/connection-profile/{datasource_id}"))


def _initialize(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS connection_profiles (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            provider TEXT NOT NULL CHECK(provider IN ('mysql', 'postgresql', 'sqlite')),
            host TEXT,
            port INTEGER,
            username TEXT,
            password_credential_ref TEXT,
            connection_mode TEXT NOT NULL DEFAULT 'direct',
            is_read_only INTEGER NOT NULL DEFAULT 0,
            environment TEXT NOT NULL DEFAULT 'dev',
            ssh_enabled INTEGER NOT NULL DEFAULT 0,
            ssh_host TEXT,
            ssh_port INTEGER,
            ssh_username TEXT,
            ssh_password_credential_ref TEXT,
            ssh_pkey_path TEXT,
            ssh_key_passphrase_credential_ref TEXT,
            ssl_enabled INTEGER NOT NULL DEFAULT 0,
            ssl_ca_path TEXT,
            ssl_cert_path TEXT,
            ssl_key_path TEXT,
            ssl_verify_identity INTEGER NOT NULL DEFAULT 1,
            connection_generation INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, name)
        );
        CREATE TABLE IF NOT EXISTS database_resources (
            id TEXT PRIMARY KEY,
            connection_profile_id TEXT NOT NULL
                REFERENCES connection_profiles(id) ON DELETE CASCADE,
            database_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            resource_generation INTEGER NOT NULL DEFAULT 1,
            catalog_revision INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(connection_profile_id, database_name)
        );
        CREATE INDEX IF NOT EXISTS ix_connection_profiles_project
            ON connection_profiles(project_id, created_at, id);
        CREATE INDEX IF NOT EXISTS ix_database_resources_profile
            ON database_resources(connection_profile_id, created_at, id);
        PRAGMA user_version = 1;
        """
    )


def _iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _assert_or_insert(
    connection: sqlite3.Connection,
    *,
    table: str,
    key: str,
    columns: tuple[str, ...],
    values: tuple[object, ...],
) -> bool:
    existing = connection.execute(
        f"SELECT {', '.join(columns)} FROM {table} WHERE id = ?", (key,)
    ).fetchone()
    canonical = tuple(values)
    if existing is not None:
        if tuple(existing) != canonical:
            raise RuntimeError(f"Conflicting staged dbfox.data row: {table}:{key}")
        return False
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        canonical,
    )
    return True


def migrate_legacy_data_sources(
    source: Session,
    *,
    data_path: Path,
) -> DataDlcImportResult:
    rows = source.query(DataSource).order_by(DataSource.created_at, DataSource.id).all()
    data_path.mkdir(parents=True, exist_ok=True)
    database_path = data_path / "state.sqlite3"
    imported_profiles = 0
    imported_databases = 0
    with sqlite3.connect(database_path) as target:
        _initialize(target)
        for datasource in rows:
            datasource_id = str(datasource.id)
            profile_id = _profile_id(datasource_id)
            project_id = str(datasource.project_id or DEFAULT_PROJECT_ID)
            created_at = _iso(datasource.created_at)
            updated_at = _iso(datasource.updated_at)
            profile_columns = (
                "id", "project_id", "name", "provider", "host", "port", "username",
                "password_credential_ref", "connection_mode", "is_read_only", "environment",
                "ssh_enabled", "ssh_host", "ssh_port", "ssh_username",
                "ssh_password_credential_ref", "ssh_pkey_path",
                "ssh_key_passphrase_credential_ref", "ssl_enabled", "ssl_ca_path",
                "ssl_cert_path", "ssl_key_path", "ssl_verify_identity",
                "connection_generation", "status", "created_at", "updated_at",
            )
            profile_values = (
                profile_id, project_id, str(datasource.name), str(datasource.db_type),
                datasource.host, datasource.port, datasource.username,
                datasource.password_credential_id, str(datasource.connection_mode or "direct"),
                int(bool(datasource.is_read_only)), str(datasource.env or "dev"),
                int(bool(datasource.ssh_enabled)), datasource.ssh_host, datasource.ssh_port,
                datasource.ssh_username, datasource.ssh_password_credential_id,
                datasource.ssh_pkey_path, datasource.ssh_key_passphrase_credential_id,
                int(bool(datasource.ssl_enabled)), datasource.ssl_ca_path,
                datasource.ssl_cert_path, datasource.ssl_key_path,
                int(bool(datasource.ssl_verify_identity)),
                int(datasource.connection_generation or 1), str(datasource.status or "active"),
                created_at, updated_at,
            )
            if _assert_or_insert(
                target,
                table="connection_profiles",
                key=profile_id,
                columns=profile_columns,
                values=profile_values,
            ):
                imported_profiles += 1
            database_columns = (
                "id", "connection_profile_id", "database_name", "display_name",
                "resource_generation", "catalog_revision", "status", "created_at", "updated_at",
            )
            database_values = (
                datasource_id, profile_id, str(datasource.database_name), str(datasource.name),
                1, int(datasource.catalog_revision or 0), str(datasource.status or "active"),
                created_at, updated_at,
            )
            if _assert_or_insert(
                target,
                table="database_resources",
                key=datasource_id,
                columns=database_columns,
                values=database_values,
            ):
                imported_databases += 1
        target.commit()
    return DataDlcImportResult(
        source_row_count=len(rows),
        imported_profile_count=imported_profiles,
        imported_database_count=imported_databases,
    )
