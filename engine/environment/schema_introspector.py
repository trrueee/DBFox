"""Introspect real databases and produce a SchemaInventory.

Supports SQLite, MySQL, PostgreSQL, and DuckDB.
"""
from __future__ import annotations

import logging
import ssl
from typing import Any, Mapping

from sqlalchemy.orm import Session

from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.environment.authoritative_inventory import (
    AuthoritativeInventory,
    SchemaInspectionError,
    SchemaInspectionErrorCode,
)
from engine.errors import DataSourceConnectionError
from engine.security.credential_vault import CredentialVaultUnavailableError
from engine.environment.datasource_resolver import (
    ResolvedDataSource,
    resolve_datasource,
)
from engine.environment.inventory import (
    ColumnInventory,
    ForeignKeyInventory,
    SchemaInventory,
    TableInventory,
)

logger = logging.getLogger("dbfox.environment.schema_introspector")


def _connection_error_code(exc: Exception) -> SchemaInspectionErrorCode:
    """Classify only stable exception types; never inspect secret-bearing text."""
    if isinstance(exc, ssl.SSLError):
        return SchemaInspectionErrorCode.TLS_FAILED
    return SchemaInspectionErrorCode.CONNECTION_FAILED


class SchemaIntrospector:
    """Introspect a live datasource into one complete authoritative snapshot."""

    def __init__(self, *, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connection_factory

    def _factory(self) -> ConnectionFactory:
        return self._connection_factory or ConnectionFactory()

    def inspect(self, db: Session, datasource_id: str) -> AuthoritativeInventory:
        from engine.models import DataSource
        from engine.datasource import datasource_connection_dict

        try:
            resolved = resolve_datasource(db, datasource_id)
        except Exception:
            raise SchemaInspectionError(
                datasource_id,
                SchemaInspectionErrorCode.DATASOURCE_NOT_FOUND,
            ) from None

        ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
        if ds is None:
            raise SchemaInspectionError(
                datasource_id,
                SchemaInspectionErrorCode.DATASOURCE_NOT_FOUND,
            )

        profile: ConnectionProfile | None = None
        try:
            if resolved.dialect == "sqlite":
                profile = ConnectionProfile.from_mapping(datasource_connection_dict(ds))
                inventory = self._inspect_sqlite(resolved, profile, self._factory())
            elif resolved.dialect == "mysql":
                if not ds.password_credential_id:
                    raise SchemaInspectionError(
                        datasource_id,
                        SchemaInspectionErrorCode.CREDENTIAL_UNAVAILABLE,
                    )
                profile = ConnectionProfile.from_mapping(datasource_connection_dict(ds))
                inventory = self._inspect_mysql(resolved, profile, self._factory())
            elif resolved.dialect == "postgres":
                if not ds.password_credential_id:
                    raise SchemaInspectionError(
                        datasource_id,
                        SchemaInspectionErrorCode.CREDENTIAL_UNAVAILABLE,
                    )
                profile = ConnectionProfile.from_mapping(datasource_connection_dict(ds))
                inventory = self._inspect_postgres(resolved, profile, self._factory())
            elif resolved.dialect == "duckdb":
                profile = ConnectionProfile.from_mapping(datasource_connection_dict(ds))
                if profile.database_name.strip() == ":memory:":
                    raise SchemaInspectionError(
                        datasource_id,
                        SchemaInspectionErrorCode.DUCKDB_MEMORY_UNSUPPORTED,
                    )
                inventory = self._inspect_duckdb(resolved, profile, self._factory())
            else:
                raise SchemaInspectionError(
                    datasource_id,
                    SchemaInspectionErrorCode.INSPECTION_FAILED,
                )
        except SchemaInspectionError:
            raise
        except CredentialVaultUnavailableError:
            raise SchemaInspectionError(
                datasource_id,
                SchemaInspectionErrorCode.CREDENTIAL_UNAVAILABLE,
            ) from None
        except DataSourceConnectionError:
            raise SchemaInspectionError(
                datasource_id,
                (
                    SchemaInspectionErrorCode.SSH_FAILED
                    if profile is not None and profile.ssh_enabled
                    else (
                        SchemaInspectionErrorCode.TLS_FAILED
                        if profile is not None and profile.ssl_enabled
                        else SchemaInspectionErrorCode.CONNECTION_FAILED
                    )
                ),
            ) from None
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.UNEXPECTED,
                exc=exc,
                level="warning",
            )
            raise SchemaInspectionError(
                datasource_id,
                SchemaInspectionErrorCode.INSPECTION_FAILED,
            ) from None

        return AuthoritativeInventory.from_completed_inventory(
            inventory,
            generation=int(getattr(ds, "generation", 0) or 0),
        )

    # ------------------------------------------------------------------
    # Shared template
    # ------------------------------------------------------------------

    @staticmethod
    def _build_inventory(
        resolved: ResolvedDataSource,
        tables: list[TableInventory],
        database_name: str,
    ) -> SchemaInventory:
        return SchemaInventory(
            datasource_id=resolved.datasource_id,
            dialect=resolved.dialect,
            database_name=database_name,
            tables=tables,
            table_count=len(tables),
            column_count=sum(len(t.columns) for t in tables),
        )

    # ------------------------------------------------------------------
    # SQLite
    # ------------------------------------------------------------------

    def _inspect_sqlite(
        self,
        resolved: ResolvedDataSource,
        profile: ConnectionProfile,
        factory: ConnectionFactory,
    ) -> SchemaInventory:
        import sqlite3

        try:
            db_path = factory.sqlite_path(profile)
        except DataSourceConnectionError:
            raise SchemaInspectionError(
                resolved.datasource_id,
                SchemaInspectionErrorCode.SQLITE_PATH_UNAVAILABLE,
            ) from None

        try:
            with factory.connection_scope(
                profile,
                purpose=ConnectionPurpose.SCHEMA_SYNC,
                read_only=True,
                sqlite_row_factory=sqlite3.Row,
            ) as conn:
                return self._build_inventory(resolved, self._sqlite_tables(conn), str(db_path))
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.UNEXPECTED,
                exc=exc,
                level="warning",
            )
            raise SchemaInspectionError(
                resolved.datasource_id,
                _connection_error_code(exc),
            ) from None

    def _sqlite_tables(self, conn: Any) -> list[TableInventory]:
        tables: list[TableInventory] = []
        rows = conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        for row in rows:
            table_name = row["name"]
            table_type = row["type"]
            columns = self._sqlite_columns(conn, table_name)
            foreign_keys = self._sqlite_foreign_keys(conn, table_name)
            sample_rows = self._sqlite_sample(conn, table_name)
            row_count = conn.execute(
                f'SELECT COUNT(*) FROM {_quote_sql_identifier(table_name)}'
            ).fetchone()[0]
            tables.append(
                TableInventory(
                    table_name=table_name,
                    table_schema="main",
                    table_type=table_type,
                    columns=columns,
                    foreign_keys=foreign_keys,
                    sample_rows=sample_rows,
                    row_count_estimate=row_count,
                )
            )
        return tables

    def _sqlite_columns(self, conn: Any, table_name: str) -> list[ColumnInventory]:
        columns: list[ColumnInventory] = []
        rows = conn.execute(f"PRAGMA table_info({_quote_sql_identifier(table_name)})").fetchall()
        # col: cid, name, type, notnull, dflt_value, pk
        for col in rows:
            columns.append(
                ColumnInventory(
                    column_name=col["name"],
                    data_type=str(col["type"] or ""),
                    column_type=str(col["type"] or ""),
                    is_nullable=not bool(col["notnull"]),
                    column_default=str(col["dflt_value"]) if col["dflt_value"] is not None else None,
                    is_primary_key=bool(col["pk"]),
                )
            )
        return columns

    def _sqlite_foreign_keys(self, conn: Any, table_name: str) -> list[ForeignKeyInventory]:
        fks: list[ForeignKeyInventory] = []
        rows = conn.execute(f"PRAGMA foreign_key_list({_quote_sql_identifier(table_name)})").fetchall()
        # col: id, seq, table, from, to, on_update, on_delete, match
        for fk in rows:
            fks.append(
                ForeignKeyInventory(
                    column_name=fk["from"],
                    referenced_table=fk["table"],
                    referenced_column=fk["to"],
                )
            )
        return fks

    def _sqlite_sample(self, conn: Any, table_name: str, limit: int = 3) -> list[dict[str, Any]]:
        try:
            rows = conn.execute(
                f"SELECT * FROM {_quote_sql_identifier(table_name)} LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # MySQL
    # ------------------------------------------------------------------

    def _inspect_mysql(
        self,
        resolved: ResolvedDataSource,
        profile: ConnectionProfile,
        factory: ConnectionFactory,
    ) -> SchemaInventory:
        try:
            with factory.connection_scope(
                profile,
                purpose=ConnectionPurpose.SCHEMA_SYNC,
                read_only=True,
            ) as conn:
                return self._build_inventory(
                    resolved,
                    self._mysql_tables(conn, resolved.database or ""),
                    resolved.database or "",
                )
        except CredentialVaultUnavailableError:
            raise
        except DataSourceConnectionError:
            raise
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.SCHEMA_INTROSPECTION_MYSQL_CONNECT,
                exc=exc,
                level="warning",
            )
            raise SchemaInspectionError(
                resolved.datasource_id,
                _connection_error_code(exc),
            ) from None

    def _mysql_tables(self, conn: Any, database: str) -> list[TableInventory]:
        tables: list[TableInventory] = []
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TABLE_NAME, TABLE_TYPE, TABLE_COMMENT, TABLE_ROWS "
            "FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE IN ('BASE TABLE', 'VIEW') "
            "ORDER BY TABLE_NAME",
            (database,),
        )
        for row in cursor.fetchall():
            table_name = _row_value(row, 0, "TABLE_NAME")
            table_type = _row_value(row, 1, "TABLE_TYPE")
            comment = _row_value(row, 2, "TABLE_COMMENT")
            table_rows = _row_value(row, 3, "TABLE_ROWS")
            columns = self._mysql_columns(cursor, database, table_name)
            fks = self._mysql_foreign_keys(cursor, database, table_name)
            sample = self._mysql_sample(conn, table_name)
            row_count = int(table_rows) if table_rows is not None else 0
            tables.append(
                TableInventory(
                    table_name=table_name,
                    table_type="view" if "VIEW" in (table_type or "") else "table",
                    comment=comment,
                    columns=columns,
                    foreign_keys=fks,
                    sample_rows=sample,
                    row_count_estimate=row_count,
                )
            )
        return tables

    def _mysql_columns(self, cursor: Any, database: str, table_name: str) -> list[ColumnInventory]:
        columns: list[ColumnInventory] = []
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
            "COLUMN_KEY, COLUMN_COMMENT "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION",
            (database, table_name),
        )
        for row in cursor.fetchall():
            col_name = _row_value(row, 0, "COLUMN_NAME")
            data_type = _row_value(row, 1, "DATA_TYPE")
            col_type = _row_value(row, 2, "COLUMN_TYPE")
            nullable = _row_value(row, 3, "IS_NULLABLE")
            default = _row_value(row, 4, "COLUMN_DEFAULT")
            col_key = _row_value(row, 5, "COLUMN_KEY")
            col_comment = _row_value(row, 6, "COLUMN_COMMENT")
            columns.append(
                ColumnInventory(
                    column_name=col_name,
                    data_type=data_type,
                    column_type=col_type,
                    is_nullable=nullable == "YES",
                    column_default=default,
                    is_primary_key=col_key == "PRI",
                    is_foreign_key=col_key == "MUL",
                    column_comment=col_comment,
                )
            )
        return columns

    def _mysql_foreign_keys(self, cursor: Any, database: str, table_name: str) -> list[ForeignKeyInventory]:
        fks: list[ForeignKeyInventory] = []
        cursor.execute(
            "SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
            "FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "AND REFERENCED_TABLE_NAME IS NOT NULL",
            (database, table_name),
        )
        for row in cursor.fetchall():
            col_name = _row_value(row, 0, "COLUMN_NAME")
            ref_table = _row_value(row, 1, "REFERENCED_TABLE_NAME")
            ref_col = _row_value(row, 2, "REFERENCED_COLUMN_NAME")
            fks.append(
                ForeignKeyInventory(
                    column_name=col_name,
                    referenced_table=ref_table,
                    referenced_column=ref_col,
                )
            )
        return fks

    def _mysql_sample(self, conn: Any, table_name: str, limit: int = 3) -> list[dict[str, Any]]:
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT * FROM {_quote_sql_identifier(table_name, '`')} LIMIT %s",
                (limit,),
            )
            rows = cursor.fetchall()
            if rows and isinstance(rows[0], Mapping):
                return [dict(row) for row in rows]
            col_names = [desc[0] for desc in cursor.description]
            return [dict(zip(col_names, row)) for row in rows]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------

    def _inspect_postgres(
        self,
        resolved: ResolvedDataSource,
        profile: ConnectionProfile,
        factory: ConnectionFactory,
    ) -> SchemaInventory:
        try:
            with factory.connection_scope(
                profile,
                purpose=ConnectionPurpose.SCHEMA_SYNC,
                read_only=True,
            ) as conn:
                return self._build_inventory(
                    resolved,
                    self._postgres_tables(conn),
                    resolved.database or resolved.safe_display_name,
                )
        except CredentialVaultUnavailableError:
            raise
        except DataSourceConnectionError:
            raise
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.UNEXPECTED,
                exc=exc,
                level="warning",
            )
            raise SchemaInspectionError(
                resolved.datasource_id,
                _connection_error_code(exc),
            ) from None

    def _postgres_tables(self, conn: Any) -> list[TableInventory]:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                t.table_schema,
                t.table_name,
                t.table_type,
                COALESCE(pg_catalog.obj_description(c.oid), '') AS table_comment,
                COALESCE(c.reltuples::bigint, 0) AS row_count_estimate
            FROM information_schema.tables t
            LEFT JOIN pg_catalog.pg_namespace n
                ON n.nspname = t.table_schema
            LEFT JOIN pg_catalog.pg_class c
                ON c.relname = t.table_name AND c.relnamespace = n.oid
            WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
              AND t.table_type IN ('BASE TABLE', 'VIEW')
            ORDER BY t.table_schema, t.table_name
            """
        )
        tables: list[TableInventory] = []
        for schema, table_name, table_type, comment, row_count in cursor.fetchall():
            columns = self._postgres_columns(conn, str(schema), str(table_name))
            fks = self._postgres_foreign_keys(conn, str(schema), str(table_name))
            sample = self._sql_sample(conn, str(table_name), schema=str(schema), quote='"')
            tables.append(
                TableInventory(
                    table_schema=str(schema),
                    table_name=str(table_name),
                    table_type="view" if "VIEW" in str(table_type or "") else "table",
                    comment=str(comment) if comment else None,
                    columns=columns,
                    foreign_keys=fks,
                    sample_rows=sample,
                    row_count_estimate=int(row_count or 0),
                )
            )
        return tables

    def _postgres_columns(self, conn: Any, schema: str, table_name: str) -> list[ColumnInventory]:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                c.column_name,
                c.data_type,
                c.udt_name,
                c.is_nullable,
                c.column_default,
                EXISTS (
                    SELECT 1
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                      AND tc.table_schema = c.table_schema
                      AND tc.table_name = c.table_name
                      AND kcu.column_name = c.column_name
                ) AS is_primary_key,
                EXISTS (
                    SELECT 1
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_schema = c.table_schema
                      AND tc.table_name = c.table_name
                      AND kcu.column_name = c.column_name
                ) AS is_foreign_key,
                COALESCE(pg_catalog.col_description(pg_class_c.oid, c.ordinal_position), '') AS column_comment
            FROM information_schema.columns c
            LEFT JOIN pg_catalog.pg_namespace pg_n
                ON pg_n.nspname = c.table_schema
            LEFT JOIN pg_catalog.pg_class pg_class_c
                ON pg_class_c.relname = c.table_name AND pg_class_c.relnamespace = pg_n.oid
            WHERE c.table_schema = %s AND c.table_name = %s
            ORDER BY c.ordinal_position
            """,
            (schema, table_name),
        )
        return [
            ColumnInventory(
                column_name=str(col_name),
                data_type=str(data_type or ""),
                column_type=str(column_type or data_type or ""),
                is_nullable=str(nullable).upper() == "YES",
                column_default=str(default) if default is not None else None,
                is_primary_key=bool(is_pk),
                is_foreign_key=bool(is_fk),
                column_comment=str(col_comment) if col_comment else None,
            )
            for col_name, data_type, column_type, nullable, default, is_pk, is_fk, col_comment in cursor.fetchall()
        ]

    def _postgres_foreign_keys(self, conn: Any, schema: str, table_name: str) -> list[ForeignKeyInventory]:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                kcu.column_name,
                ccu.table_name AS referenced_table,
                ccu.column_name AS referenced_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s
              AND tc.table_name = %s
            ORDER BY kcu.ordinal_position
            """,
            (schema, table_name),
        )
        return [
            ForeignKeyInventory(
                column_name=str(col_name),
                referenced_table=str(ref_table),
                referenced_column=str(ref_col),
            )
            for col_name, ref_table, ref_col in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # DuckDB
    # ------------------------------------------------------------------

    def _inspect_duckdb(
        self,
        resolved: ResolvedDataSource,
        profile: ConnectionProfile,
        factory: ConnectionFactory,
    ) -> SchemaInventory:
        try:
            with factory.connection_scope(
                profile,
                purpose=ConnectionPurpose.SCHEMA_SYNC,
                read_only=True,
            ) as conn:
                return self._build_inventory(
                    resolved,
                    self._duckdb_tables(conn),
                    str(profile.database_name),
                )
        except DataSourceConnectionError:
            raise SchemaInspectionError(
                resolved.datasource_id,
                (
                    SchemaInspectionErrorCode.DUCKDB_MEMORY_UNSUPPORTED
                    if profile.database_name.strip() == ":memory:"
                    else SchemaInspectionErrorCode.DUCKDB_PATH_UNAVAILABLE
                ),
            ) from None
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.SCHEMA_INTROSPECTION_DUCKDB_CONNECT,
                exc=exc,
                level="warning",
            )
            raise SchemaInspectionError(
                resolved.datasource_id,
                SchemaInspectionErrorCode.CONNECTION_FAILED,
            ) from None

    def _duckdb_tables(self, conn: Any) -> list[TableInventory]:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT table_schema, table_name, table_type, ''
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
              AND table_type IN ('BASE TABLE', 'VIEW')
            ORDER BY table_schema, table_name
            """
        )
        tables: list[TableInventory] = []
        for schema, table_name, table_type, comment in cursor.fetchall():
            schema_str = str(schema)
            table_str = str(table_name)
            columns = self._duckdb_columns(conn, schema_str, table_str)
            fks = self._duckdb_foreign_keys(conn, schema_str, table_str)
            sample = self._sql_sample(conn, table_str, schema=schema_str, quote='"')
            row_count = self._sql_row_count(conn, table_str, schema=schema_str, quote='"')
            tables.append(
                TableInventory(
                    table_schema=schema_str,
                    table_name=table_str,
                    table_type="view" if "VIEW" in str(table_type or "") else "table",
                    comment=str(comment) if comment else None,
                    columns=columns,
                    foreign_keys=fks,
                    sample_rows=sample,
                    row_count_estimate=row_count,
                )
            )
        return tables

    def _duckdb_columns(self, conn: Any, schema: str, table_name: str) -> list[ColumnInventory]:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                column_name,
                data_type,
                data_type,
                is_nullable,
                column_default,
                false AS is_primary_key,
                false AS is_foreign_key
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            (schema, table_name),
        )
        columns = [
            ColumnInventory(
                column_name=str(col_name),
                data_type=str(data_type or ""),
                column_type=str(column_type or data_type or ""),
                is_nullable=str(nullable).upper() == "YES",
                column_default=str(default) if default is not None else None,
                is_primary_key=bool(is_pk),
                is_foreign_key=bool(is_fk),
            )
            for col_name, data_type, column_type, nullable, default, is_pk, is_fk in cursor.fetchall()
        ]

        # ---- Resolve real primary keys via table_constraints ----
        cursor.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = ?
              AND tc.table_name = ?
            """,
            (schema, table_name),
        )
        pk_rows = cursor.fetchall()
        pk_cols = {str(r[0]) for r in pk_rows}

        # ---- Resolve real foreign keys ----
        fk_cols = {fk.column_name for fk in self._duckdb_foreign_keys(conn, schema, table_name)}

        for column in columns:
            if column.column_name in pk_cols:
                column.is_primary_key = True
            if column.column_name in fk_cols:
                column.is_foreign_key = True

        return columns

    def _duckdb_foreign_keys(self, conn: Any, schema: str, table_name: str) -> list[ForeignKeyInventory]:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT column_name, referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = ? AND table_name = ?
              AND referenced_table_name IS NOT NULL
            ORDER BY ordinal_position
            """,
            (schema, table_name),
        )
        return [
            ForeignKeyInventory(
                column_name=str(col_name),
                referenced_table=str(ref_table),
                referenced_column=str(ref_col),
            )
            for col_name, ref_table, ref_col in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # SQL helpers
    # ------------------------------------------------------------------

    def _sql_sample(
        self,
        conn: Any,
        table_name: str,
        *,
        schema: str = "",
        quote: str = '"',
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT * FROM {_qualified_name(schema, table_name, quote)} LIMIT {limit}"
            )
            col_names = [desc[0] for desc in cursor.description]
            return [dict(zip(col_names, row)) for row in cursor.fetchall()]
        except Exception:
            return []

    def _sql_row_count(self, conn: Any, table_name: str, *, schema: str = "", quote: str = '"') -> int | None:
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {_qualified_name(schema, table_name, quote)}")
            row = cursor.fetchone()
            return int(row[0]) if row else None
        except Exception:
            return None

# Module-level convenience
def introspect_datasource(db: Session, datasource_id: str) -> AuthoritativeInventory:
    return SchemaIntrospector().inspect(db, datasource_id)


def _quote_sql_identifier(identifier: str, quote: str = '"') -> str:
    return quote + identifier.replace(quote, quote + quote) + quote


def _row_value(row: Any, index: int, key: str) -> Any:
    """Read both DB-API tuples and the factory's MySQL DictCursor rows."""
    if isinstance(row, Mapping):
        return row.get(key)
    return row[index]


def _qualified_name(schema: str, table: str, quote: str = '"') -> str:
    if schema:
        return f"{_quote_sql_identifier(schema, quote)}.{_quote_sql_identifier(table, quote)}"
    return _quote_sql_identifier(table, quote)
