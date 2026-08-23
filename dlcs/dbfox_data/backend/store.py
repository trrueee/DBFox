from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from dbfox_dlc_api import ProjectResourceDescriptor, ResourceScopeRef, json_dumps

from .contracts import (
    BackupRecord,
    ConnectionProfile,
    DatabaseHandle,
    DatabaseResource,
    ProfileWithDatabases,
)
from .inventory import SchemaInventory, SyncResult
from .resource_kind import DATABASE_RESOURCE_KIND


_NETWORK_PROVIDERS = frozenset({"mysql", "postgresql"})


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validated_profile_values(
    *,
    provider: str,
    host: str | None,
    port: int | None,
    username: str | None,
    password_credential_ref: str | None,
    ssh_enabled: bool,
    ssh_host: str | None,
    ssh_port: int | None,
    ssh_username: str | None,
    ssh_password_credential_ref: str | None,
    ssh_pkey_path: str | None,
    ssh_key_passphrase_credential_ref: str | None,
    ssl_enabled: bool,
    ssl_ca_path: str | None,
    ssl_cert_path: str | None,
    ssl_key_path: str | None,
    ssl_verify_identity: bool,
) -> dict[str, object]:
    values: dict[str, object] = {
        "host": _clean_optional(host),
        "port": port,
        "username": _clean_optional(username),
        "password_credential_ref": _clean_optional(password_credential_ref),
        "ssh_enabled": bool(ssh_enabled),
        "ssh_host": _clean_optional(ssh_host),
        "ssh_port": ssh_port,
        "ssh_username": _clean_optional(ssh_username),
        "ssh_password_credential_ref": _clean_optional(ssh_password_credential_ref),
        "ssh_pkey_path": _clean_optional(ssh_pkey_path),
        "ssh_key_passphrase_credential_ref": _clean_optional(ssh_key_passphrase_credential_ref),
        "ssl_enabled": bool(ssl_enabled),
        "ssl_ca_path": _clean_optional(ssl_ca_path),
        "ssl_cert_path": _clean_optional(ssl_cert_path),
        "ssl_key_path": _clean_optional(ssl_key_path),
        "ssl_verify_identity": bool(ssl_verify_identity),
    }
    if provider == "sqlite":
        forbidden = (
            "host", "port", "username", "password_credential_ref", "ssh_host",
            "ssh_port", "ssh_username", "ssh_password_credential_ref",
            "ssh_pkey_path", "ssh_key_passphrase_credential_ref", "ssl_ca_path",
            "ssl_cert_path", "ssl_key_path",
        )
        if values["ssh_enabled"] or values["ssl_enabled"] or any(values[key] is not None for key in forbidden):
            raise ValueError("SQLite connection profiles cannot contain network, SSH, TLS, or credential settings")
        return values
    if provider not in _NETWORK_PROVIDERS:
        raise ValueError("Unsupported database provider")
    if values["host"] is None:
        raise ValueError("Network connection profiles require a host")
    if values["username"] is None:
        raise ValueError("Network connection profiles require a username")
    if values["password_credential_ref"] is None:
        raise ValueError("Network connection profiles require a password credential reference")
    if port is None:
        values["port"] = 5432 if provider == "postgresql" else 3306
    if values["ssh_enabled"]:
        values["ssh_port"] = ssh_port or 22
        if values["ssh_host"] is None or values["ssh_username"] is None:
            raise ValueError("SSH-enabled profiles require an SSH host and username")
        if values["ssh_password_credential_ref"] is None and values["ssh_pkey_path"] is None:
            raise ValueError("SSH-enabled profiles require a password credential or private key")
    elif any(values[key] is not None for key in (
        "ssh_host", "ssh_port", "ssh_username", "ssh_password_credential_ref",
        "ssh_pkey_path", "ssh_key_passphrase_credential_ref",
    )):
        raise ValueError("SSH settings require ssh_enabled")
    if bool(values["ssl_cert_path"]) != bool(values["ssl_key_path"]):
        raise ValueError("TLS client certificate and key must be configured together")
    if not values["ssl_enabled"] and any(values[key] is not None for key in (
        "ssl_ca_path", "ssl_cert_path", "ssl_key_path",
    )):
        raise ValueError("TLS paths require ssl_enabled")
    return values


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _scope_version(profile_generation: int, resource_generation: int) -> str:
    return f"{profile_generation}:{resource_generation}"


@dataclass(frozen=True)
class StoredResultPage:
    result_id: str
    database_resource_id: str
    resource_version: str
    query_fingerprint: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    source_truncated: bool


@dataclass(frozen=True)
class StoredBackup:
    record: BackupRecord
    file_name: str


class DataStateStore:
    def __init__(self, data_path: Path) -> None:
        data_path.mkdir(parents=True, exist_ok=True)
        self.database_path = data_path / "state.sqlite3"
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
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
                """
            )
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version < 2:
                columns = {
                    str(row[1])
                    for row in connection.execute(
                        "PRAGMA table_info(database_resources)"
                    ).fetchall()
                }
                if "catalog_refreshed_at" not in columns:
                    connection.execute(
                        "ALTER TABLE database_resources ADD COLUMN catalog_refreshed_at TEXT"
                    )
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS catalog_tables (
                        id TEXT PRIMARY KEY,
                        database_resource_id TEXT NOT NULL
                            REFERENCES database_resources(id) ON DELETE CASCADE,
                        schema_name TEXT NOT NULL,
                        table_name TEXT NOT NULL,
                        object_type TEXT NOT NULL,
                        comment TEXT,
                        row_count_estimate INTEGER,
                        UNIQUE(database_resource_id, schema_name, table_name)
                    );
                    CREATE INDEX IF NOT EXISTS ix_catalog_tables_database_order
                        ON catalog_tables(database_resource_id, schema_name, table_name, id);

                    CREATE TABLE IF NOT EXISTS catalog_columns (
                        table_id TEXT NOT NULL
                            REFERENCES catalog_tables(id) ON DELETE CASCADE,
                        ordinal_position INTEGER NOT NULL,
                        column_name TEXT NOT NULL,
                        data_type TEXT,
                        column_type TEXT,
                        is_nullable INTEGER NOT NULL,
                        column_default TEXT,
                        is_primary_key INTEGER NOT NULL,
                        is_foreign_key INTEGER NOT NULL,
                        comment TEXT,
                        PRIMARY KEY(table_id, column_name)
                    );
                    CREATE INDEX IF NOT EXISTS ix_catalog_columns_name
                        ON catalog_columns(column_name, table_id);

                    CREATE TABLE IF NOT EXISTS catalog_foreign_keys (
                        table_id TEXT NOT NULL
                            REFERENCES catalog_tables(id) ON DELETE CASCADE,
                        column_name TEXT NOT NULL,
                        referenced_schema TEXT NOT NULL DEFAULT '',
                        referenced_table TEXT NOT NULL,
                        referenced_column TEXT NOT NULL,
                        PRIMARY KEY(
                            table_id, column_name, referenced_schema,
                            referenced_table, referenced_column
                        )
                    );
                    PRAGMA user_version = 2;
                    """
                )
            if version < 3:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS query_results (
                        id TEXT PRIMARY KEY,
                        database_resource_id TEXT NOT NULL
                            REFERENCES database_resources(id) ON DELETE CASCADE,
                        resource_version TEXT NOT NULL,
                        query_fingerprint TEXT NOT NULL,
                        columns_json TEXT NOT NULL,
                        row_count INTEGER NOT NULL CHECK(row_count >= 0),
                        source_truncated INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_query_results_database_created
                        ON query_results(database_resource_id, created_at, id);

                    CREATE TABLE IF NOT EXISTS query_result_rows (
                        result_id TEXT NOT NULL
                            REFERENCES query_results(id) ON DELETE CASCADE,
                        row_index INTEGER NOT NULL CHECK(row_index >= 0),
                        row_json TEXT NOT NULL,
                        PRIMARY KEY(result_id, row_index)
                    );
                    PRAGMA user_version = 3;
                    """
                )
            if version < 4:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS backups (
                        id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        database_resource_id TEXT NOT NULL
                            REFERENCES database_resources(id) ON DELETE CASCADE,
                        resource_version TEXT NOT NULL,
                        label TEXT,
                        backup_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        file_size_bytes INTEGER,
                        checksum_sha256 TEXT,
                        source_database_name TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS ix_backups_project_created
                        ON backups(project_id, started_at, id);
                    CREATE INDEX IF NOT EXISTS ix_backups_database_created
                        ON backups(database_resource_id, started_at, id);

                    CREATE TABLE IF NOT EXISTS restore_operations (
                        id TEXT PRIMARY KEY,
                        backup_id TEXT NOT NULL REFERENCES backups(id) ON DELETE CASCADE,
                        database_resource_id TEXT NOT NULL
                            REFERENCES database_resources(id) ON DELETE CASCADE,
                        status TEXT NOT NULL,
                        source_database_name TEXT NOT NULL,
                        target_database_name TEXT NOT NULL,
                        previous_resource_version TEXT NOT NULL,
                        committed_resource_version TEXT NOT NULL,
                        validated_table_count INTEGER NOT NULL,
                        completed_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_restore_operations_database
                        ON restore_operations(database_resource_id, completed_at, id);
                    PRAGMA user_version = 4;
                    """
                )
            elif version > 4:
                raise RuntimeError("Data state schema is newer than this DBFox build")

    @staticmethod
    def _profile(row: sqlite3.Row) -> ConnectionProfile:
        return ConnectionProfile.model_validate(dict(row))

    @staticmethod
    def _database(row: sqlite3.Row) -> DatabaseResource:
        return DatabaseResource.model_validate(dict(row))

    @staticmethod
    def _backup(row: sqlite3.Row) -> StoredBackup:
        values = dict(row)
        file_name = str(values.pop("file_name"))
        return StoredBackup(
            record=BackupRecord.model_validate(values),
            file_name=file_name,
        )

    def list_profiles(self, project_id: str) -> tuple[ConnectionProfile, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM connection_profiles WHERE project_id = ? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return tuple(self._profile(row) for row in rows)

    def get_profile(self, profile_id: str) -> ConnectionProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM connection_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        return self._profile(row) if row is not None else None

    def list_databases(self, profile_id: str) -> tuple[DatabaseResource, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM database_resources WHERE connection_profile_id = ? ORDER BY created_at, id",
                (profile_id,),
            ).fetchall()
        return tuple(self._database(row) for row in rows)

    def get_database(self, database_id: str) -> DatabaseResource | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM database_resources WHERE id = ?", (database_id,)
            ).fetchone()
        return self._database(row) if row is not None else None

    @staticmethod
    def _catalog_table_id(
        database_resource_id: str,
        schema_name: str,
        table_name: str,
    ) -> str:
        identity = "\x00".join((database_resource_id, schema_name, table_name))
        return f"catalog_table_{sha256(identity.encode('utf-8')).hexdigest()[:32]}"

    def replace_catalog(self, inventory: SchemaInventory) -> SyncResult:
        """Atomically replace one database catalog and advance its revision."""

        database_id = inventory.database_resource_id
        database = self.get_database(database_id)
        if database is None:
            raise KeyError("Database resource is unavailable")
        new_tables = {
            (table.table_schema, table.table_name)
            for table in inventory.tables
        }
        new_columns = {
            (table.table_schema, table.table_name, column.column_name)
            for table in inventory.tables
            for column in table.columns
        }
        refreshed_at = _now()
        with self._connect() as connection, connection:
            old_tables = {
                (str(row["schema_name"]), str(row["table_name"]))
                for row in connection.execute(
                    """
                    SELECT schema_name, table_name
                      FROM catalog_tables
                     WHERE database_resource_id = ?
                    """,
                    (database_id,),
                ).fetchall()
            }
            old_columns = {
                (
                    str(row["schema_name"]),
                    str(row["table_name"]),
                    str(row["column_name"]),
                )
                for row in connection.execute(
                    """
                    SELECT t.schema_name, t.table_name, c.column_name
                      FROM catalog_columns c
                      JOIN catalog_tables t ON t.id = c.table_id
                     WHERE t.database_resource_id = ?
                    """,
                    (database_id,),
                ).fetchall()
            }
            connection.execute(
                "DELETE FROM catalog_tables WHERE database_resource_id = ?",
                (database_id,),
            )
            for table in inventory.tables:
                table_id = self._catalog_table_id(
                    database_id,
                    table.table_schema,
                    table.table_name,
                )
                connection.execute(
                    """
                    INSERT INTO catalog_tables (
                        id, database_resource_id, schema_name, table_name,
                        object_type, comment, row_count_estimate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        table_id,
                        database_id,
                        table.table_schema,
                        table.table_name,
                        table.table_type,
                        table.comment,
                        table.row_count_estimate,
                    ),
                )
                for position, column in enumerate(table.columns):
                    connection.execute(
                        """
                        INSERT INTO catalog_columns (
                            table_id, ordinal_position, column_name, data_type,
                            column_type, is_nullable, column_default,
                            is_primary_key, is_foreign_key, comment
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            table_id,
                            position,
                            column.column_name,
                            column.data_type,
                            column.column_type,
                            int(column.is_nullable),
                            column.column_default,
                            int(column.is_primary_key),
                            int(column.is_foreign_key),
                            column.column_comment,
                        ),
                    )
                for foreign_key in table.foreign_keys:
                    connection.execute(
                        """
                        INSERT INTO catalog_foreign_keys (
                            table_id, column_name, referenced_schema,
                            referenced_table, referenced_column
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            table_id,
                            foreign_key.column_name,
                            foreign_key.referenced_schema or "",
                            foreign_key.referenced_table,
                            foreign_key.referenced_column,
                        ),
                    )
            cursor = connection.execute(
                """
                UPDATE database_resources
                   SET catalog_revision = catalog_revision + 1,
                       catalog_refreshed_at = ?, updated_at = ?
                 WHERE id = ?
                """,
                (refreshed_at, refreshed_at, database_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Database resource became unavailable during refresh")
            revision = int(
                connection.execute(
                    "SELECT catalog_revision FROM database_resources WHERE id = ?",
                    (database_id,),
                ).fetchone()[0]
            )
        return SyncResult(
            database_resource_id=database_id,
            tables_created=len(new_tables - old_tables),
            tables_updated=len(new_tables & old_tables),
            tables_removed=len(old_tables - new_tables),
            columns_created=len(new_columns - old_columns),
            columns_updated=len(new_columns & old_columns),
            columns_removed=len(old_columns - new_columns),
            synced=True,
            catalog_revision=revision,
        )

    def catalog_state(self, database_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            database = connection.execute(
                """
                SELECT d.catalog_revision, d.catalog_refreshed_at,
                       d.display_name, p.provider
                  FROM database_resources d
                  JOIN connection_profiles p ON p.id = d.connection_profile_id
                 WHERE d.id = ?
                """,
                (database_id,),
            ).fetchone()
            if database is None:
                raise KeyError("Database resource is unavailable")
            counts = connection.execute(
                """
                SELECT COUNT(*) AS table_count,
                       COUNT(DISTINCT schema_name) AS schema_count
                  FROM catalog_tables
                 WHERE database_resource_id = ?
                """,
                (database_id,),
            ).fetchone()
            schemas = [
                {
                    "name": str(row["schema_name"]),
                    "table_count": int(row["table_count"]),
                }
                for row in connection.execute(
                    """
                    SELECT schema_name, COUNT(*) AS table_count
                      FROM catalog_tables
                     WHERE database_resource_id = ?
                     GROUP BY schema_name
                     ORDER BY schema_name
                    """,
                    (database_id,),
                ).fetchall()
            ]
        return {
            "database_id": database_id,
            "database_name": str(database["display_name"]),
            "dialect": str(database["provider"]),
            "catalog_revision": int(database["catalog_revision"] or 0),
            "refreshed_at": database["catalog_refreshed_at"],
            "table_count": int(counts["table_count"] or 0),
            "schema_count": int(counts["schema_count"] or 0),
            "schemas": schemas,
        }

    def list_catalog_tables(
        self,
        database_id: str,
        *,
        after: tuple[str, str, str] | None,
        limit: int,
        name_filter: str | None,
    ) -> tuple[list[dict[str, Any]], bool]:
        clauses = ["t.database_resource_id = ?"]
        parameters: list[object] = [database_id]
        if after is not None:
            schema_name, table_name, table_id = after
            clauses.append(
                "(t.schema_name > ? OR (t.schema_name = ? AND t.table_name > ?) "
                "OR (t.schema_name = ? AND t.table_name = ? AND t.id > ?))"
            )
            parameters.extend(
                (schema_name, schema_name, table_name, schema_name, table_name, table_id)
            )
        if name_filter:
            clauses.append("lower(t.table_name) LIKE ?")
            parameters.append(f"%{name_filter.casefold()}%")
        parameters.append(limit + 1)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT t.id, t.schema_name, t.table_name, t.object_type,
                       t.comment, t.row_count_estimate, COUNT(c.column_name) AS columns_count
                  FROM catalog_tables t
                  LEFT JOIN catalog_columns c ON c.table_id = t.id
                 WHERE {' AND '.join(clauses)}
                 GROUP BY t.id
                 ORDER BY t.schema_name, t.table_name, t.id
                 LIMIT ?
                """,
                tuple(parameters),
            ).fetchall()
        return [dict(row) for row in rows[:limit]], len(rows) > limit

    def resolve_catalog_table(
        self,
        database_id: str,
        name: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        normalized = name.strip()
        if not normalized or "\x00" in normalized:
            raise ValueError("A valid catalog table name is required")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                  FROM catalog_tables
                 WHERE database_resource_id = ?
                   AND (
                       table_name = ?
                       OR schema_name || '.' || table_name = ?
                   )
                 ORDER BY schema_name, table_name, id
                 LIMIT 2
                """,
                (database_id, normalized, normalized),
            ).fetchall()
            if len(rows) > 1:
                raise ValueError(
                    "Ambiguous table name; use the qualified_name returned by schema_list"
                )
            if not rows:
                raise KeyError("Table is unavailable in the current catalog")
            table = dict(rows[0])
            columns = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT *
                      FROM catalog_columns
                     WHERE table_id = ?
                     ORDER BY ordinal_position, column_name
                    """,
                    (table["id"],),
                ).fetchall()
            ]
        return table, columns

    def search_catalog(
        self,
        database_id: str,
        tokens: tuple[str, ...],
        limit: int,
    ) -> list[dict[str, Any]]:
        if not tokens:
            return []
        token_patterns = tuple(f"%{token.casefold()}%" for token in tokens)
        table_clauses = " OR ".join(
            "lower(t.table_name || ' ' || coalesce(t.comment, '')) LIKE ?"
            for _ in tokens
        )
        column_clauses = " OR ".join(
            "lower(c.column_name || ' ' || coalesce(c.comment, '')) LIKE ?"
            for _ in tokens
        )
        candidate_limit = min(limit * 3, 60)
        with self._connect() as connection:
            table_rows = connection.execute(
                f"""
                SELECT 'table' AS type, t.schema_name, t.table_name,
                       NULL AS column_name, t.table_name AS name, t.comment
                  FROM catalog_tables t
                 WHERE t.database_resource_id = ? AND ({table_clauses})
                 ORDER BY t.schema_name, t.table_name
                 LIMIT ?
                """,
                (database_id, *token_patterns, candidate_limit),
            ).fetchall()
            column_rows = connection.execute(
                f"""
                SELECT 'column' AS type, t.schema_name, t.table_name,
                       c.column_name,
                       t.table_name || '.' || c.column_name AS name,
                       c.comment
                  FROM catalog_columns c
                  JOIN catalog_tables t ON t.id = c.table_id
                 WHERE t.database_resource_id = ? AND ({column_clauses})
                 ORDER BY t.schema_name, t.table_name, c.ordinal_position
                 LIMIT ?
                """,
                (database_id, *token_patterns, candidate_limit),
            ).fetchall()
        ranked: list[dict[str, Any]] = []
        for row in (*table_rows, *column_rows):
            item = dict(row)
            searchable = " ".join(
                str(item.get(key) or "")
                for key in ("name", "comment")
            ).casefold()
            name = str(item.get("name") or "").casefold()
            name_hits = sum(token.casefold() in name for token in tokens)
            text_hits = sum(token.casefold() in searchable for token in tokens)
            item["score"] = float(name_hits * 3 + text_hits)
            item["reasons"] = ["catalog_name_or_comment_match"]
            item["matched_fields"] = [
                "column_name" if item["type"] == "column" else "table_name"
            ]
            item.pop("comment", None)
            ranked.append(item)
        ranked.sort(
            key=lambda item: (
                -float(item["score"]),
                str(item["type"]),
                str(item["schema_name"]),
                str(item["name"]),
            )
        )
        return ranked[:limit]

    def save_query_result(
        self,
        *,
        database_resource_id: str,
        resource_version: str,
        query_fingerprint: str,
        columns: list[str],
        rows: list[dict[str, Any]],
        source_truncated: bool,
    ) -> str:
        """Persist an already-bounded execution result and return an opaque reference."""

        if self.get_database(database_resource_id) is None:
            raise KeyError("Database resource is unavailable")
        normalized_version = str(resource_version).strip()
        normalized_fingerprint = str(query_fingerprint).strip()
        if not normalized_version or not normalized_fingerprint:
            raise ValueError("Stored query results require resource and query identities")
        result_id = f"data_result_{uuid4().hex}"
        with self._connect() as connection, connection:
            connection.execute(
                """
                INSERT INTO query_results (
                    id, database_resource_id, resource_version,
                    query_fingerprint, columns_json, row_count,
                    source_truncated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    database_resource_id,
                    normalized_version,
                    normalized_fingerprint,
                    json_dumps([str(column) for column in columns]),
                    len(rows),
                    int(source_truncated),
                    _now(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO query_result_rows (result_id, row_index, row_json)
                VALUES (?, ?, ?)
                """,
                (
                    (result_id, index, json_dumps(row))
                    for index, row in enumerate(rows)
                ),
            )
        return result_id

    def load_query_result_page(
        self,
        result_id: str,
        *,
        offset: int,
        limit: int,
    ) -> StoredResultPage:
        """Read durable Data-owned rows without reexecuting source SQL."""

        if offset < 0 or limit < 1:
            raise ValueError("Result page bounds are invalid")
        with self._connect() as connection:
            record = connection.execute(
                """
                SELECT id, database_resource_id, resource_version,
                       query_fingerprint, columns_json, row_count,
                       source_truncated
                  FROM query_results
                 WHERE id = ?
                """,
                (result_id,),
            ).fetchone()
            if record is None:
                raise KeyError("Stored query result is unavailable")
            row_records = connection.execute(
                """
                SELECT row_json
                  FROM query_result_rows
                 WHERE result_id = ? AND row_index >= ?
                 ORDER BY row_index
                 LIMIT ?
                """,
                (result_id, offset, limit),
            ).fetchall()
        columns_value = json.loads(str(record["columns_json"]))
        if not isinstance(columns_value, list) or not all(
            isinstance(column, str) for column in columns_value
        ):
            raise RuntimeError("Stored query result columns are invalid")
        rows: list[dict[str, Any]] = []
        for row_record in row_records:
            row_value = json.loads(str(row_record["row_json"]))
            if not isinstance(row_value, dict):
                raise RuntimeError("Stored query result row is invalid")
            rows.append({str(key): value for key, value in row_value.items()})
        return StoredResultPage(
            result_id=str(record["id"]),
            database_resource_id=str(record["database_resource_id"]),
            resource_version=str(record["resource_version"]),
            query_fingerprint=str(record["query_fingerprint"]),
            columns=list(columns_value),
            rows=rows,
            row_count=int(record["row_count"]),
            source_truncated=bool(record["source_truncated"]),
        )

    def create_backup_record(
        self,
        *,
        project_id: str,
        database_resource_id: str,
        resource_version: str,
        source_database_name: str,
        label: str | None,
        file_name: str,
    ) -> StoredBackup:
        backup_id = f"data_backup_{uuid4().hex}"
        started_at = _now()
        with self._connect() as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO backups (
                    id, project_id, database_resource_id, resource_version,
                    label, backup_type, status, file_name,
                    source_database_name, started_at
                )
                SELECT ?, ?, d.id, ?, ?, 'sqlite_online_backup', 'running', ?,
                       ?, ?
                 FROM database_resources d
                  JOIN connection_profiles p ON p.id = d.connection_profile_id
                 WHERE d.id = ? AND p.project_id = ?
                   AND (p.connection_generation || ':' || d.resource_generation) = ?
                """,
                (
                    backup_id,
                    project_id,
                    resource_version,
                    _clean_optional(label),
                    file_name,
                    source_database_name,
                    started_at,
                    database_resource_id,
                    project_id,
                    resource_version,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError("Database resource is unavailable in this Project")
            row = connection.execute(
                "SELECT * FROM backups WHERE id = ?", (backup_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Backup record was not persisted")
        return self._backup(row)

    def complete_backup_record(
        self,
        backup_id: str,
        *,
        file_size_bytes: int,
        checksum_sha256: str,
    ) -> StoredBackup:
        completed_at = _now()
        with self._connect() as connection, connection:
            cursor = connection.execute(
                """
                UPDATE backups
                   SET status = 'success', file_size_bytes = ?,
                       checksum_sha256 = ?, completed_at = ?
                 WHERE id = ? AND status = 'running'
                """,
                (file_size_bytes, checksum_sha256, completed_at, backup_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Backup record is not running")
            row = connection.execute(
                "SELECT * FROM backups WHERE id = ?", (backup_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Backup record is unavailable")
        return self._backup(row)

    def fail_backup_record(self, backup_id: str) -> None:
        with self._connect() as connection, connection:
            connection.execute(
                """
                UPDATE backups
                   SET status = 'failed', completed_at = ?
                 WHERE id = ? AND status = 'running'
                """,
                (_now(), backup_id),
            )

    def list_backups(
        self,
        project_id: str,
        database_id: str | None = None,
    ) -> tuple[BackupRecord, ...]:
        query = "SELECT * FROM backups WHERE project_id = ?"
        parameters: list[Any] = [project_id]
        if database_id is not None:
            query += " AND database_resource_id = ?"
            parameters.append(database_id)
        query += " ORDER BY started_at DESC, id DESC"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return tuple(self._backup(row).record for row in rows)

    def get_backup(self, project_id: str, backup_id: str) -> StoredBackup | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM backups WHERE id = ? AND project_id = ?",
                (backup_id, project_id),
            ).fetchone()
        return self._backup(row) if row is not None else None

    def commit_sqlite_restore(
        self,
        *,
        project_id: str,
        backup_id: str,
        database_resource_id: str,
        expected_resource_version: str,
        source_database_name: str,
        target_database_name: str,
        validated_table_count: int,
    ) -> dict[str, Any]:
        restore_id = f"data_restore_{uuid4().hex}"
        completed_at = _now()
        with self._connect() as connection, connection:
            row = connection.execute(
                """
                SELECT d.resource_generation, p.connection_generation
                  FROM database_resources d
                  JOIN connection_profiles p ON p.id = d.connection_profile_id
                 WHERE d.id = ? AND p.project_id = ? AND p.provider = 'sqlite'
                """,
                (database_resource_id, project_id),
            ).fetchone()
            if row is None:
                raise KeyError("SQLite database resource is unavailable")
            current_version = _scope_version(
                int(row["connection_generation"]),
                int(row["resource_generation"]),
            )
            if current_version != expected_resource_version:
                raise ValueError("Database resource version changed before restore cutover")
            new_generation = int(row["resource_generation"]) + 1
            committed_version = _scope_version(
                int(row["connection_generation"]),
                new_generation,
            )
            connection.execute(
                """
                UPDATE database_resources
                   SET database_name = ?, resource_generation = ?,
                       catalog_revision = 0, catalog_refreshed_at = NULL,
                       updated_at = ?
                 WHERE id = ?
                """,
                (
                    target_database_name,
                    new_generation,
                    completed_at,
                    database_resource_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO restore_operations (
                    id, backup_id, database_resource_id, status,
                    source_database_name, target_database_name,
                    previous_resource_version, committed_resource_version,
                    validated_table_count, completed_at
                ) VALUES (?, ?, ?, 'success', ?, ?, ?, ?, ?, ?)
                """,
                (
                    restore_id,
                    backup_id,
                    database_resource_id,
                    source_database_name,
                    target_database_name,
                    current_version,
                    committed_version,
                    validated_table_count,
                    completed_at,
                ),
            )
        return {
            "id": restore_id,
            "committed_resource_version": committed_version,
            "completed_at": completed_at,
        }

    def list_profile_groups(self, project_id: str) -> tuple[ProfileWithDatabases, ...]:
        return tuple(
            ProfileWithDatabases(
                profile=profile,
                databases=self.list_databases(profile.id),
            )
            for profile in self.list_profiles(project_id)
        )

    def create_profile(
        self,
        *,
        project_id: str,
        name: str,
        provider: str,
        host: str | None,
        port: int | None,
        username: str | None,
        password_credential_ref: str | None,
        is_read_only: bool,
        environment: str,
        ssh_enabled: bool,
        ssh_host: str | None,
        ssh_port: int | None,
        ssh_username: str | None,
        ssh_password_credential_ref: str | None,
        ssh_pkey_path: str | None,
        ssh_key_passphrase_credential_ref: str | None,
        ssl_enabled: bool,
        ssl_ca_path: str | None,
        ssl_cert_path: str | None,
        ssl_key_path: str | None,
        ssl_verify_identity: bool,
        initial_database_name: str | None = None,
        initial_database_display_name: str | None = None,
    ) -> ProfileWithDatabases:
        connection_values = _validated_profile_values(
            provider=provider,
            host=host,
            port=port,
            username=username,
            password_credential_ref=password_credential_ref,
            ssh_enabled=ssh_enabled,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_username=ssh_username,
            ssh_password_credential_ref=ssh_password_credential_ref,
            ssh_pkey_path=ssh_pkey_path,
            ssh_key_passphrase_credential_ref=ssh_key_passphrase_credential_ref,
            ssl_enabled=ssl_enabled,
            ssl_ca_path=ssl_ca_path,
            ssl_cert_path=ssl_cert_path,
            ssl_key_path=ssl_key_path,
            ssl_verify_identity=ssl_verify_identity,
        )
        profile_id = str(uuid4())
        database_id = str(uuid4()) if initial_database_name else None
        now = _now()
        try:
            with self._connect() as sqlite_connection, sqlite_connection:
                sqlite_connection.execute(
                    """
                    INSERT INTO connection_profiles (
                        id, project_id, name, provider, host, port, username,
                        password_credential_ref, is_read_only, environment,
                        ssh_enabled, ssh_host, ssh_port, ssh_username,
                        ssh_password_credential_ref, ssh_pkey_path,
                        ssh_key_passphrase_credential_ref, ssl_enabled, ssl_ca_path,
                        ssl_cert_path, ssl_key_path, ssl_verify_identity,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id, project_id, name.strip(), provider,
                        connection_values["host"], connection_values["port"], connection_values["username"],
                        connection_values["password_credential_ref"], int(is_read_only), environment,
                        int(bool(connection_values["ssh_enabled"])), connection_values["ssh_host"],
                        connection_values["ssh_port"], connection_values["ssh_username"],
                        connection_values["ssh_password_credential_ref"], connection_values["ssh_pkey_path"],
                        connection_values["ssh_key_passphrase_credential_ref"],
                        int(bool(connection_values["ssl_enabled"])), connection_values["ssl_ca_path"],
                        connection_values["ssl_cert_path"], connection_values["ssl_key_path"],
                        int(bool(connection_values["ssl_verify_identity"])), now, now,
                    ),
                )
                if database_id is not None and initial_database_name is not None:
                    sqlite_connection.execute(
                        """
                        INSERT INTO database_resources (
                            id, connection_profile_id, database_name, display_name,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            database_id,
                            profile_id,
                            initial_database_name,
                            initial_database_display_name or initial_database_name,
                            now,
                            now,
                        ),
                    )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Connection profile or initial database already exists") from exc
        profile = self.get_profile(profile_id)
        if profile is None:
            raise RuntimeError("Created connection profile could not be reloaded")
        return ProfileWithDatabases(profile=profile, databases=self.list_databases(profile_id))

    def update_profile(
        self,
        *,
        project_id: str,
        profile_id: str,
        expected_generation: int,
        name: str,
        host: str | None,
        port: int | None,
        username: str | None,
        password_credential_ref: str | None,
        is_read_only: bool,
        environment: str,
        ssh_enabled: bool,
        ssh_host: str | None,
        ssh_port: int | None,
        ssh_username: str | None,
        ssh_password_credential_ref: str | None,
        ssh_pkey_path: str | None,
        ssh_key_passphrase_credential_ref: str | None,
        ssl_enabled: bool,
        ssl_ca_path: str | None,
        ssl_cert_path: str | None,
        ssl_key_path: str | None,
        ssl_verify_identity: bool,
    ) -> ProfileWithDatabases:
        current = self.get_profile(profile_id)
        if current is None or current.project_id != project_id:
            raise ValueError("Connection profile is unavailable in this project")
        connection_values = _validated_profile_values(
            provider=current.provider,
            host=host,
            port=port,
            username=username,
            password_credential_ref=password_credential_ref,
            ssh_enabled=ssh_enabled,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_username=ssh_username,
            ssh_password_credential_ref=ssh_password_credential_ref,
            ssh_pkey_path=ssh_pkey_path,
            ssh_key_passphrase_credential_ref=ssh_key_passphrase_credential_ref,
            ssl_enabled=ssl_enabled,
            ssl_ca_path=ssl_ca_path,
            ssl_cert_path=ssl_cert_path,
            ssl_key_path=ssl_key_path,
            ssl_verify_identity=ssl_verify_identity,
        )
        with self._connect() as sqlite_connection, sqlite_connection:
            cursor = sqlite_connection.execute(
                """
                UPDATE connection_profiles
                   SET name = ?, host = ?, port = ?, username = ?,
                       password_credential_ref = ?, is_read_only = ?, environment = ?,
                       ssh_enabled = ?, ssh_host = ?, ssh_port = ?, ssh_username = ?,
                       ssh_password_credential_ref = ?, ssh_pkey_path = ?,
                       ssh_key_passphrase_credential_ref = ?, ssl_enabled = ?,
                       ssl_ca_path = ?, ssl_cert_path = ?, ssl_key_path = ?,
                       ssl_verify_identity = ?,
                       connection_generation = connection_generation + 1,
                       updated_at = ?
                 WHERE id = ? AND project_id = ? AND connection_generation = ?
                """,
                (
                    name.strip(), connection_values["host"], connection_values["port"],
                    connection_values["username"], connection_values["password_credential_ref"],
                    int(is_read_only), environment, int(bool(connection_values["ssh_enabled"])),
                    connection_values["ssh_host"], connection_values["ssh_port"],
                    connection_values["ssh_username"], connection_values["ssh_password_credential_ref"],
                    connection_values["ssh_pkey_path"], connection_values["ssh_key_passphrase_credential_ref"],
                    int(bool(connection_values["ssl_enabled"])), connection_values["ssl_ca_path"],
                    connection_values["ssl_cert_path"], connection_values["ssl_key_path"],
                    int(bool(connection_values["ssl_verify_identity"])),
                    _now(), profile_id, project_id,
                    expected_generation,
                ),
            )
        if cursor.rowcount != 1:
            raise ValueError("Connection profile generation is stale or profile is unavailable")
        profile = self.get_profile(profile_id)
        if profile is None:
            raise RuntimeError("Updated connection profile could not be reloaded")
        return ProfileWithDatabases(profile=profile, databases=self.list_databases(profile_id))

    def add_database(
        self,
        *,
        project_id: str,
        profile_id: str,
        database_name: str,
        display_name: str | None,
    ) -> DatabaseResource:
        profile = self.get_profile(profile_id)
        if profile is None or profile.project_id != project_id:
            raise KeyError("Connection profile is unavailable in this project")
        database_id = str(uuid4())
        now = _now()
        try:
            with self._connect() as connection, connection:
                connection.execute(
                    """
                    INSERT INTO database_resources (
                        id, connection_profile_id, database_name, display_name,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (database_id, profile_id, database_name, display_name or database_name, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Database already exists on this connection profile") from exc
        database = self.get_database(database_id)
        if database is None:
            raise RuntimeError("Created database resource could not be reloaded")
        return database

    def update_database(
        self,
        *,
        project_id: str,
        database_id: str,
        expected_generation: int,
        database_name: str,
        display_name: str,
    ) -> DatabaseResource:
        with self._connect() as connection, connection:
            cursor = connection.execute(
                """
                UPDATE database_resources
                   SET database_name = ?, display_name = ?,
                       resource_generation = resource_generation + 1,
                       updated_at = ?
                 WHERE id = ? AND resource_generation = ?
                   AND connection_profile_id IN (
                       SELECT id FROM connection_profiles WHERE project_id = ?
                   )
                """,
                (
                    database_name.strip(), display_name.strip(), _now(), database_id,
                    expected_generation, project_id,
                ),
            )
        if cursor.rowcount != 1:
            raise ValueError("Database resource generation is stale or resource is unavailable")
        database = self.get_database(database_id)
        if database is None:
            raise RuntimeError("Updated database resource could not be reloaded")
        return database

    def delete_database(self, project_id: str, database_id: str) -> bool:
        with self._connect() as connection, connection:
            cursor = connection.execute(
                """
                DELETE FROM database_resources
                 WHERE id = ? AND connection_profile_id IN (
                    SELECT id FROM connection_profiles WHERE project_id = ?
                 )
                """,
                (database_id, project_id),
            )
        return cursor.rowcount == 1

    def delete_profile(self, project_id: str, profile_id: str) -> bool:
        with self._connect() as connection, connection:
            cursor = connection.execute(
                "DELETE FROM connection_profiles WHERE id = ? AND project_id = ?",
                (profile_id, project_id),
            )
        return cursor.rowcount == 1

    def owns_credential_references(self, credential_refs: frozenset[str]) -> bool:
        """Return whether durable Data state owns every supplied opaque ref."""

        if not credential_refs:
            return False
        placeholders = ", ".join("?" for _ in credential_refs)
        parameters = tuple(sorted(credential_refs))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT password_credential_ref,
                       ssh_password_credential_ref,
                       ssh_key_passphrase_credential_ref
                  FROM connection_profiles
                 WHERE password_credential_ref IN ({placeholders})
                    OR ssh_password_credential_ref IN ({placeholders})
                    OR ssh_key_passphrase_credential_ref IN ({placeholders})
                """,
                parameters * 3,
            ).fetchall()
        owned = {
            str(value)
            for row in rows
            for value in row
            if value is not None and str(value) in credential_refs
        }
        return owned == credential_refs

    def list_resources(self, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        descriptors: list[ProjectResourceDescriptor] = []
        for group in self.list_profile_groups(project_id):
            for database in group.databases:
                if database.status != "active" or group.profile.status != "active":
                    continue
                descriptors.append(
                    ProjectResourceDescriptor(
                        kind=DATABASE_RESOURCE_KIND,
                        id=database.id,
                        version=_scope_version(
                            group.profile.connection_generation,
                            database.resource_generation,
                        ),
                        name=database.display_name,
                    )
                )
        return tuple(descriptors)

    def resolve(self, ref: ResourceScopeRef) -> DatabaseHandle:
        if ref.kind != DATABASE_RESOURCE_KIND:
            raise KeyError(f"Unexpected resource kind: {ref.kind}")
        database = self.get_database(str(ref.id))
        if database is None:
            raise ValueError(f"Database resource '{ref.id}' does not exist")
        profile = self.get_profile(database.connection_profile_id)
        if profile is None:
            raise ValueError(f"Connection profile for database '{ref.id}' does not exist")
        version = _scope_version(profile.connection_generation, database.resource_generation)
        if str(ref.version or "") != version:
            raise ValueError(f"Database resource '{ref.id}' version does not match authorized scope")
        return DatabaseHandle(profile=profile, database=database, scope_version=version)
