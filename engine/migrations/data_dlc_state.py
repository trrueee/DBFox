"""One-way cutover of legacy Core datasource identities into dbfox.data state."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session


DEFAULT_PROJECT_ID = "default-project"


class DataDlcMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DataDlcImportResult:
    source_row_count: int
    imported_profile_count: int
    imported_database_count: int


def _metadata_database_path(bind: Engine | Connection) -> Path:
    engine = bind.engine if isinstance(bind, Connection) else bind
    if engine.dialect.name != "sqlite" or not engine.url.database:
        raise DataDlcMigrationError(
            "Data DLC migration requires a file-backed SQLite database"
        )
    return Path(engine.url.database).resolve()


def data_dlc_data_path(bind: Engine | Connection) -> Path:
    metadata_path = _metadata_database_path(bind)
    from engine.db import DB_PATH
    from engine.runtime_paths import private_runtime_dir

    if metadata_path == DB_PATH.resolve():
        storage_root = private_runtime_dir("dlcs")
    else:
        storage_root = metadata_path.parent / "dlcs"
        storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root / "data" / "dbfox.data"


def _profile_id(datasource_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"dbfox.data/connection-profile/{datasource_id}"))


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return datetime.fromisoformat(value).isoformat()
    raise DataDlcMigrationError("Historical Data timestamp is invalid")


def _legacy_rows(source: Session | Connection) -> list[dict[str, Any]]:
    rows = source.execute(text("""
        SELECT id, project_id, name, db_type, host, port, database_name,
               username, password_credential_id, connection_mode,
               is_read_only, env, ssh_enabled, ssh_host, ssh_port,
               ssh_username, ssh_password_credential_id, ssh_pkey_path,
               ssh_key_passphrase_credential_id, ssl_enabled, ssl_ca_path,
               ssl_cert_path, ssl_key_path, ssl_verify_identity,
               connection_generation, status, created_at, updated_at
          FROM data_sources
         ORDER BY created_at, id
    """)).mappings()
    return [_canonical_row(row) for row in rows]


def _canonical_row(row: RowMapping | sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    datasource_id = str(value["id"])
    return {
        "datasource_id": datasource_id,
        "profile_id": _profile_id(datasource_id),
        "project_id": str(value.get("project_id") or DEFAULT_PROJECT_ID),
        "name": str(value["name"]),
        "provider": str(value["db_type"]),
        "host": value.get("host"),
        "port": value.get("port"),
        "database_name": str(value["database_name"]),
        "username": value.get("username"),
        "password_credential_ref": value.get("password_credential_id"),
        "connection_mode": str(value.get("connection_mode") or "direct"),
        "is_read_only": int(bool(value.get("is_read_only"))),
        "environment": str(value.get("env") or "dev"),
        "ssh_enabled": int(bool(value.get("ssh_enabled"))),
        "ssh_host": value.get("ssh_host"),
        "ssh_port": value.get("ssh_port"),
        "ssh_username": value.get("ssh_username"),
        "ssh_password_credential_ref": value.get("ssh_password_credential_id"),
        "ssh_pkey_path": value.get("ssh_pkey_path"),
        "ssh_key_passphrase_credential_ref": value.get(
            "ssh_key_passphrase_credential_id"
        ),
        "ssl_enabled": int(bool(value.get("ssl_enabled"))),
        "ssl_ca_path": value.get("ssl_ca_path"),
        "ssl_cert_path": value.get("ssl_cert_path"),
        "ssl_key_path": value.get("ssl_key_path"),
        "ssl_verify_identity": int(bool(value.get("ssl_verify_identity"))),
        "connection_generation": int(value.get("connection_generation") or 1),
        "status": str(value.get("status") or "active"),
        "created_at": _timestamp(value["created_at"]),
        "updated_at": _timestamp(value["updated_at"]),
    }


class DataLegacyImportTarget:
    def __init__(self, data_path: Path) -> None:
        data_path.mkdir(parents=True, exist_ok=True)
        self.database_path = data_path / "state.sqlite3"
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript("""
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
                CREATE INDEX IF NOT EXISTS ix_connection_profiles_project
                    ON connection_profiles(project_id, created_at, id);
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
                CREATE INDEX IF NOT EXISTS ix_database_resources_profile
                    ON database_resources(connection_profile_id, created_at, id);
                CREATE TABLE IF NOT EXISTS legacy_core_import_rows (
                    datasource_id TEXT PRIMARY KEY
                );
            """)
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version == 0:
                connection.execute("PRAGMA user_version = 1")
            elif version > 4:
                raise DataDlcMigrationError(
                    "Data DLC state is newer than this DBFox migration"
                )

    @staticmethod
    def _profile(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["profile_id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "provider": row["provider"],
            "host": row["host"],
            "port": row["port"],
            "username": row["username"],
            "password_credential_ref": row["password_credential_ref"],
            "connection_mode": row["connection_mode"],
            "is_read_only": row["is_read_only"],
            "environment": row["environment"],
            "ssh_enabled": row["ssh_enabled"],
            "ssh_host": row["ssh_host"],
            "ssh_port": row["ssh_port"],
            "ssh_username": row["ssh_username"],
            "ssh_password_credential_ref": row["ssh_password_credential_ref"],
            "ssh_pkey_path": row["ssh_pkey_path"],
            "ssh_key_passphrase_credential_ref": row[
                "ssh_key_passphrase_credential_ref"
            ],
            "ssl_enabled": row["ssl_enabled"],
            "ssl_ca_path": row["ssl_ca_path"],
            "ssl_cert_path": row["ssl_cert_path"],
            "ssl_key_path": row["ssl_key_path"],
            "ssl_verify_identity": row["ssl_verify_identity"],
            "connection_generation": row["connection_generation"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _database(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["datasource_id"],
            "connection_profile_id": row["profile_id"],
            "database_name": row["database_name"],
            "display_name": row["name"],
            "resource_generation": 1,
            # Legacy catalog rows are derived state and are intentionally rebuilt.
            "catalog_revision": 0,
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _assert_equal_or_insert(
        connection: sqlite3.Connection,
        *,
        table: str,
        row: dict[str, Any],
    ) -> bool:
        existing = connection.execute(
            f"SELECT {', '.join(row)} FROM {table} WHERE id = ?", (row["id"],)
        ).fetchone()
        expected = tuple(row.values())
        if existing is not None:
            if tuple(existing) != expected:
                raise DataDlcMigrationError(
                    f"Data DLC target contains a conflicting row: {table}:{row['id']}"
                )
            return False
        connection.execute(
            f"INSERT INTO {table} ({', '.join(row)}) VALUES "
            f"({', '.join('?' for _ in row)})",
            expected,
        )
        return True

    def sync(self, rows: Sequence[dict[str, Any]]) -> tuple[int, int]:
        profiles = 0
        databases = 0
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for row in rows:
                    profiles += int(self._assert_equal_or_insert(
                        connection, table="connection_profiles", row=self._profile(row)
                    ))
                    databases += int(self._assert_equal_or_insert(
                        connection, table="database_resources", row=self._database(row)
                    ))
                    connection.execute(
                        "INSERT OR IGNORE INTO legacy_core_import_rows(datasource_id) VALUES (?)",
                        (row["datasource_id"],),
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return profiles, databases

    def validate(self, rows: Sequence[dict[str, Any]]) -> None:
        with self._connect() as connection:
            for source in rows:
                for table, expected in (
                    ("connection_profiles", self._profile(source)),
                    ("database_resources", self._database(source)),
                ):
                    target = connection.execute(
                        f"SELECT {', '.join(expected)} FROM {table} WHERE id = ?",
                        (expected["id"],),
                    ).fetchone()
                    if target is None or tuple(target) != tuple(expected.values()):
                        raise DataDlcMigrationError(
                            "Data DLC target validation failed before Core cutover"
                        )


def migrate_legacy_data_sources(
    source: Session | Connection,
    *,
    data_path: Path | None = None,
) -> DataDlcImportResult:
    bind = source.get_bind() if isinstance(source, Session) else source
    target = DataLegacyImportTarget(data_path or data_dlc_data_path(bind))
    rows = _legacy_rows(source)
    try:
        profiles, databases = target.sync(rows)
        target.validate(rows)
    except sqlite3.Error as exc:
        raise DataDlcMigrationError("Data DLC target migration failed") from exc
    return DataDlcImportResult(
        source_row_count=len(rows),
        imported_profile_count=profiles,
        imported_database_count=databases,
    )
