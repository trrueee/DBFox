"""Introspect real databases and produce a SchemaInventory.

Supports SQLite, MySQL, and a stub for PostgreSQL / DuckDB.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from engine.crypto import decrypt_password
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

logger = logging.getLogger("databox.environment.schema_introspector")


class SchemaIntrospector:
    """Introspect a live datasource and return a SchemaInventory."""

    def inspect(self, db: Session, datasource_id: str) -> SchemaInventory:
        resolved = resolve_datasource(db, datasource_id)
        if resolved.dialect == "sqlite":
            return self._inspect_sqlite(resolved)
        if resolved.dialect == "mysql":
            return self._inspect_mysql(db, resolved)
        # Postgres / DuckDB — stub for now
        return SchemaInventory(
            datasource_id=datasource_id,
            dialect=resolved.dialect,
            database_name=resolved.safe_display_name,
        )

    # ------------------------------------------------------------------
    # SQLite
    # ------------------------------------------------------------------

    def _inspect_sqlite(self, resolved: ResolvedDataSource) -> SchemaInventory:
        import sqlite3

        db_path = resolved.database_path or ""
        if not db_path or not Path(db_path).exists():
            return SchemaInventory(
                datasource_id=resolved.datasource_id,
                dialect="sqlite",
                database_name=db_path,
            )

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            tables = self._sqlite_tables(conn)
            table_count = len(tables)
            column_count = sum(len(t.columns) for t in tables)
            return SchemaInventory(
                datasource_id=resolved.datasource_id,
                dialect="sqlite",
                database_name=db_path,
                tables=tables,
                table_count=table_count,
                column_count=column_count,
            )
        finally:
            conn.close()

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
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
            tables.append(
                TableInventory(
                    table_name=table_name,
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
        rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
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
        rows = conn.execute(f'PRAGMA foreign_key_list("{table_name}")').fetchall()
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
            rows = conn.execute(f'SELECT * FROM "{table_name}" LIMIT {limit}').fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # MySQL
    # ------------------------------------------------------------------

    def _inspect_mysql(self, db: Session, resolved: ResolvedDataSource) -> SchemaInventory:
        import pymysql

        datasource = resolved
        pw = self._decrypt_datasource_password(db, resolved.datasource_id)
        try:
            conn = pymysql.connect(
                host=datasource.host or "127.0.0.1",
                port=datasource.port or 3306,
                user=datasource.username or "root",
                password=pw,
                database=datasource.database,
                charset="utf8mb4",
                connect_timeout=10,
            )
        except Exception as exc:
            logger.warning("MySQL connect failed for %s: %s", resolved.datasource_id, exc)
            return SchemaInventory(
                datasource_id=resolved.datasource_id,
                dialect="mysql",
                database_name=resolved.safe_display_name,
            )

        try:
            tables = self._mysql_tables(conn, datasource.database or "")
            table_count = len(tables)
            column_count = sum(len(t.columns) for t in tables)
            return SchemaInventory(
                datasource_id=resolved.datasource_id,
                dialect="mysql",
                database_name=datasource.database or "",
                tables=tables,
                table_count=table_count,
                column_count=column_count,
            )
        finally:
            conn.close()

    def _mysql_tables(self, conn: Any, database: str) -> list[TableInventory]:
        tables: list[TableInventory] = []
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TABLE_NAME, TABLE_TYPE, TABLE_COMMENT "
            "FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE IN ('BASE TABLE', 'VIEW') "
            "ORDER BY TABLE_NAME",
            (database,),
        )
        for table_name, table_type, comment in cursor.fetchall():
            columns = self._mysql_columns(cursor, database, table_name)
            fks = self._mysql_foreign_keys(cursor, database, table_name)
            sample = self._mysql_sample(conn, table_name)
            cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
            row_count = cursor.fetchone()[0]
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
        for col_name, data_type, col_type, nullable, default, col_key, col_comment in cursor.fetchall():
            columns.append(
                ColumnInventory(
                    column_name=col_name,
                    data_type=data_type,
                    column_type=col_type,
                    is_nullable=nullable == "YES",
                    column_default=default,
                    is_primary_key=col_key == "PRI",
                    is_foreign_key=col_key == "MUL",
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
        for col_name, ref_table, ref_col in cursor.fetchall():
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
            cursor.execute(f"SELECT * FROM `{table_name}` LIMIT {limit}")
            col_names = [desc[0] for desc in cursor.description]
            return [dict(zip(col_names, row)) for row in cursor.fetchall()]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _decrypt_datasource_password(self, db: Session, datasource_id: str) -> str:
        row = db.query(db.get_bind()).first()  # not used; we query from passed db
        from engine.models import DataSource as DS

        ds = db.query(DS).filter(DS.id == datasource_id).first()
        if ds is None:
            return ""
        try:
            return decrypt_password(
                str(ds.password_ciphertext or ""),
                str(ds.password_nonce or ""),
            )
        except Exception:
            return ""


# Module-level convenience
def introspect_datasource(db: Session, datasource_id: str) -> SchemaInventory:
    return SchemaIntrospector().inspect(db, datasource_id)
