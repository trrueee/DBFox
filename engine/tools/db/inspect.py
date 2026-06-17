"""db.inspect — live database introspection (tables, columns, indexes, FKs)."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from threading import Lock
from typing import Any

from sqlalchemy.orm import Session
from sqlglot import exp

from engine.agent_core.tool_registry import ToolContext
from engine.agent_core.types import ToolObservation
from engine.datasource import datasource_connection_dict, get_mysql_connection_params, get_postgres_connection_params
from engine.errors import ToolInputError
from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.sql.pool_manager import get_mysql_pool, get_postgres_pool, _ping_mysql_connection
from engine.tools.db._common import (
    _catalog_table,
    _column_summary,
    _datasource,
    _ordered_columns,
    tool_handler,
)

logger = logging.getLogger("dbfox.tools.db.inspect")


@tool_handler("db.inspect")
def db_inspect(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Live introspection of a table or column from the real database.

    Connects to the live database and runs system introspection queries
    (``information_schema``, ``pg_catalog``, ``PRAGMA``) to return the
    current structure — not a stale catalog snapshot.
    """
    target = str(args.get("target") or "").strip()
    if not target:
        raise ToolInputError("target is required (table or table.column).")

    ds_id = ctx.request.datasource_id
    cache_key = (ds_id, target)
    cached_output = _INSPECT_CACHE.get(cache_key)
    if cached_output is not None:
        logger.info("db.inspect cache hit for %s", target)
        return cached_output

    ds = _datasource(ctx.db, ds_id)
    dialect = (ds.db_type or "mysql").lower()

    if dialect == "sqlite":
        output = _sqlite_inspect_detail(ctx.db, ds, target)
    elif dialect == "postgres" or dialect == "postgresql":
        output = _pg_inspect_detail(ctx.db, ds, target)
    else:
        output = _mysql_inspect_detail(ctx.db, ds, target)
    _INSPECT_CACHE.set(cache_key, output)
    return output


# ===================================================================
# db.inspect helpers  (live introspection)
# ===================================================================


def _parse_target(target: str) -> tuple[str, str | None, str | None]:
    """Parse a target reference into (table_name, column_name, schema_name).

    Supports:
      - "users"              → table, no column, no schema
      - "users.id"           → table, column, no schema
      - "public.users"       → table, no column, schema=public
      - "public.users.id"    → table, column, schema=public
    """
    parts = [p for p in target.split(".") if p]
    if len(parts) == 1:
        return parts[0], None, None
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 3:
        return parts[1], parts[2], parts[0]
    raise ValueError(f"Invalid target: {target}")


def _ds_to_dict(ds: DataSource) -> dict[str, Any]:
    """Convert ORM object to the dict expected by connection-param helpers."""
    return {
        "host": ds.host,
        "port": ds.port,
        "database_name": ds.database_name,
        "username": ds.username,
        "password_ciphertext": ds.password_ciphertext,
        "password_nonce": ds.password_nonce,
        "password_key_version": ds.password_key_version,
        "ssh_enabled": ds.ssh_enabled,
        "ssh_host": ds.ssh_host,
        "ssh_port": ds.ssh_port,
        "ssh_username": ds.ssh_username,
        "ssh_password_ciphertext": ds.ssh_password_ciphertext,
        "ssh_password_nonce": ds.ssh_password_nonce,
        "ssh_pkey_path": ds.ssh_pkey_path,
        "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
        "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
        "ssl_enabled": ds.ssl_enabled,
        "ssl_ca_path": ds.ssl_ca_path,
        "ssl_cert_path": ds.ssl_cert_path,
        "ssl_key_path": ds.ssl_key_path,
        "ssl_verify_identity": ds.ssl_verify_identity,
    }


class TTLMemoryCache:
    def __init__(self, ttl_seconds: float = 10.0, maxsize: int = 500):
        self.ttl = ttl_seconds
        self.maxsize = maxsize
        self._cache: dict[tuple, Any] = {}
        self._lock = Lock()

    def get(self, key: tuple) -> Any:
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                val, expiry = entry
                now = time.time()
                if now < expiry:
                    # Refresh LRU ordering by re-inserting
                    self._cache.pop(key)
                    self._cache[key] = (val, expiry)
                    return val
                # Lazy eviction: only delete the expired key being accessed
                del self._cache[key]
            return None

    def set(self, key: tuple, value: Any) -> None:
        with self._lock:
            # Refresh LRU ordering by removing old key if it exists
            self._cache.pop(key, None)
            self._cache[key] = (value, time.time() + self.ttl)
            if len(self._cache) > self.maxsize:
                # Evict the oldest key (first item in the dict)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]


_INSPECT_CACHE = TTLMemoryCache(ttl_seconds=10.0, maxsize=500)


def escape_identifier(name: str, dialect: str) -> str:
    """
    Safely escape a SQL identifier (table, schema, column name)
    using sqlglot.exp.to_identifier.
    """
    from engine.sql.parser import normalize_dialect
    sqlglot_dialect = normalize_dialect(dialect)
    return exp.to_identifier(name).sql(sqlglot_dialect, identify=True)


# ---- SQLite live introspection ---------------------------------------


def _sqlite_inspect_detail(db: Session, ds: DataSource, target: str) -> dict[str, Any]:
    table_name, column_name, _schema = _parse_target(target)
    path = str(ds.database_name)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        if not _sqlite_table_exists(conn, table_name):
            raise ValueError(f"Table not found: {table_name}")

        payload = _sqlite_table_payload(db, conn, ds.id, table_name)

        if column_name:
            for col in payload["columns"]:
                if col["name"] == column_name:
                    col["object_type"] = "column"
                    col["table"] = table_name
                    return col
            raise ValueError(f"Column not found: {target}")
        return payload


def _sqlite_table_payload(
    db: Session, conn: sqlite3.Connection, datasource_id: str, table_name: str
) -> dict[str, Any]:
    catalog = _catalog_table(db, datasource_id, table_name)
    comment_map: dict[str, str] = {}
    if catalog is not None:
        comment_map = {str(c.column_name): str(c.column_comment or "") for c in _ordered_columns(catalog)}

    fk_by_col = _sqlite_fk_map(conn, table_name)
    columns: list[dict[str, Any]] = []
    pk_cols: list[str] = []

    for row in conn.execute(f"PRAGMA table_info({escape_identifier(table_name, 'sqlite')})"):
        name = str(row["name"])
        is_pk = bool(row["pk"])
        if is_pk:
            pk_cols.append(name)
        columns.append({
            "name": name,
            "type": str(row["type"] or ""),
            "nullable": not bool(row["notnull"] or is_pk),
            "default": row["dflt_value"],
            "primary_key": is_pk,
            "foreign_key": fk_by_col.get(name),
            "comment": comment_map.get(name, ""),
        })

    fks_out = [
        {"column": src, "references": {"table": fk["table"], "column": fk["column"]}}
        for src, fk in sorted(fk_by_col.items())
    ]

    return {
        "object_type": "table",
        "name": table_name,
        "type": _sqlite_table_type(conn, table_name),
        "dialect": "sqlite",
        "comment": str(catalog.table_comment or "") if catalog else "",
        "row_estimate": _sqlite_row_count(conn, table_name),
        "columns": columns,
        "primary_key": pk_cols,
        "foreign_keys_out": fks_out,
        "foreign_keys_in": _sqlite_reverse_fks(conn, table_name),
        "indexes": _sqlite_indexes(conn, table_name, pk_cols),
        "source": "live",
    }


def _sqlite_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _sqlite_table_type(conn: sqlite3.Connection, name: str) -> str:
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        return "table"
    return "view" if row["type"] == "view" else "table"


def _sqlite_fk_map(conn: sqlite3.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in conn.execute(f"PRAGMA foreign_key_list({escape_identifier(table_name, 'sqlite')})"):
        result[str(row["from"])] = {"table": str(row["table"]), "column": str(row["to"])}
    return result


def _sqlite_reverse_fks(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    # Optimize: pre-filter candidate tables by checking if referenced table name exists in their creation DDL
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE ? ORDER BY name",
        (f"%{table_name}%",)
    ).fetchall()
    for t in tables:
        src = str(t["name"])
        for fk in conn.execute(f"PRAGMA foreign_key_list({escape_identifier(src, 'sqlite')})"):
            if str(fk["table"]).lower() == table_name.lower():
                result.append({
                    "table": src,
                    "column": str(fk["from"]),
                    "references": {"column": str(fk["to"])},
                })
    return result


def _sqlite_indexes(
    conn: sqlite3.Connection, table_name: str, pk_cols: list[str]
) -> list[dict[str, Any]]:
    indexes: list[dict[str, Any]] = []
    if pk_cols:
        indexes.append({"name": "PRIMARY", "columns": pk_cols, "unique": True})
    for row in conn.execute(f"PRAGMA index_list({escape_identifier(table_name, 'sqlite')})"):
        iname = str(row["name"])
        cols = [
            str(ci["name"])
            for ci in conn.execute(f"PRAGMA index_info({escape_identifier(iname, 'sqlite')})")
            if ci["name"] is not None
        ]
        indexes.append({
            "name": iname,
            "columns": cols,
            "unique": bool(row["unique"]),
        })
    return indexes


def _sqlite_row_count(conn: sqlite3.Connection, table_name: str) -> int | None:
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {escape_identifier(table_name, 'sqlite')}").fetchone()
        return int(row[0]) if row else None
    except sqlite3.Error:
        return None


# ---- MySQL live introspection ----------------------------------------


def _mysql_inspect_detail(db: Session, ds: DataSource, target: str) -> dict[str, Any]:
    table_name, column_name, _schema = _parse_target(target)
    ds_dict = _ds_to_dict(ds)

    params = get_mysql_connection_params(ds_dict)
    pool = get_mysql_pool(ds.id, params)
    conn = pool.connect()

    try:
        database = ds_dict.get("database_name", "")
        if not _mysql_table_exists(conn, database, table_name):
            raise ValueError(f"Table not found: {table_name}")

        payload = _mysql_table_payload(db, conn, ds.id, database, table_name)

        if column_name:
            for col in payload["columns"]:
                if col["name"] == column_name:
                    col["object_type"] = "column"
                    col["table"] = table_name
                    return col
            raise ValueError(f"Column not found: {target}")
        return payload
    finally:
        conn.close()


def _mysql_table_exists(conn: Any, database: str, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (database, table_name),
    )
    row = cur.fetchone()
    return row is not None


def _mysql_table_payload(
    db: Session, conn: Any, datasource_id: str, database: str, table_name: str
) -> dict[str, Any]:
    cur = conn.cursor()
    catalog = _catalog_table(db, datasource_id, table_name)
    comment_map: dict[str, str] = {}
    if catalog is not None:
        comment_map = {str(c.column_name): str(c.column_comment or "") for c in _ordered_columns(catalog)}

    # columns
    cur.execute(
        "SELECT c.COLUMN_NAME, c.DATA_TYPE, c.IS_NULLABLE, c.COLUMN_DEFAULT, "
        "       c.COLUMN_COMMENT, c.COLUMN_KEY = 'PRI' AS is_pk, "
        "       kcu.REFERENCED_TABLE_NAME, kcu.REFERENCED_COLUMN_NAME "
        "FROM information_schema.COLUMNS c "
        "LEFT JOIN information_schema.KEY_COLUMN_USAGE kcu "
        "  ON c.TABLE_SCHEMA = kcu.TABLE_SCHEMA "
        " AND c.TABLE_NAME = kcu.TABLE_NAME "
        " AND c.COLUMN_NAME = kcu.COLUMN_NAME "
        " AND kcu.REFERENCED_TABLE_NAME IS NOT NULL "
        "WHERE c.TABLE_SCHEMA = %s AND c.TABLE_NAME = %s "
        "ORDER BY c.ORDINAL_POSITION",
        (database, table_name),
    )
    columns: list[dict[str, Any]] = []
    pk_cols: list[str] = []
    fks_out: list[dict[str, Any]] = []
    for row in cur.fetchall():
        name = str(_row_value(row, 0, "COLUMN_NAME"))
        is_pk = bool(_row_value(row, 5, "is_pk"))
        if is_pk:
            pk_cols.append(name)
        fk = None
        ref_table = _row_value(row, 6, "REFERENCED_TABLE_NAME")
        ref_column = _row_value(row, 7, "REFERENCED_COLUMN_NAME")
        if ref_table:
            fk = {"table": str(ref_table), "column": str(ref_column)}
            fks_out.append({"column": name, "references": fk})
        columns.append({
            "name": name,
            "type": str(_row_value(row, 1, "DATA_TYPE")),
            "nullable": str(_row_value(row, 2, "IS_NULLABLE")).upper() == "YES",
            "default": _row_value(row, 3, "COLUMN_DEFAULT"),
            "primary_key": is_pk,
            "foreign_key": fk,
            "comment": comment_map.get(name, str(_row_value(row, 4, "COLUMN_COMMENT") or "")),
        })

    # reverse FKs
    fks_in: list[dict[str, Any]] = []
    cur.execute(
        "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_COLUMN_NAME "
        "FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME = %s",
        (database, table_name),
    )
    for row in cur.fetchall():
        fks_in.append({
            "table": str(_row_value(row, 0, "TABLE_NAME")),
            "column": str(_row_value(row, 1, "COLUMN_NAME")),
            "references": {"column": str(_row_value(row, 2, "REFERENCED_COLUMN_NAME"))},
        })

    # indexes
    indexes: list[dict[str, Any]] = []
    try:
        cur.execute(f"SHOW INDEX FROM {escape_identifier(table_name, 'mysql')} FROM {escape_identifier(database, 'mysql')}")
        index_groups: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            iname = str(_row_value(row, 2, "Key_name"))
            if iname not in index_groups:
                index_groups[iname] = {
                    "name": iname,
                    "columns": [],
                    "unique": bool(not _row_value(row, 3, "Non_unique")),
                }
            index_groups[iname]["columns"].append(str(_row_value(row, 4, "Column_name")))
        indexes = list(index_groups.values())
    except Exception:
        pass

    # row estimate
    row_est = None
    try:
        cur.execute(
            "SELECT TABLE_ROWS FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (database, table_name),
        )
        est = cur.fetchone()
        if est:
            row_est = int(_row_value(est, 0, "TABLE_ROWS") or 0)
    except Exception:
        pass

    # table comment
    table_comment = ""
    try:
        cur.execute(
            "SELECT TABLE_COMMENT FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (database, table_name),
        )
        tc = cur.fetchone()
        if tc:
            table_comment = str(_row_value(tc, 0, "TABLE_COMMENT") or "")
    except Exception:
        pass

    return {
        "object_type": "table",
        "name": table_name,
        "type": "table",
        "dialect": "mysql",
        "comment": table_comment or (str(catalog.table_comment or "") if catalog else ""),
        "row_estimate": row_est,
        "columns": columns,
        "primary_key": pk_cols,
        "foreign_keys_out": fks_out,
        "foreign_keys_in": fks_in,
        "indexes": indexes,
        "source": "live",
    }


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[index]
    except (IndexError, KeyError, TypeError):
        return None


# ---- PostgreSQL live introspection -----------------------------------


def _pg_inspect_detail(db: Session, ds: DataSource, target: str) -> dict[str, Any]:
    table_name, column_name, schema_name = _parse_target(target)
    ds_dict = _ds_to_dict(ds)

    params = get_postgres_connection_params(ds_dict)
    pool = get_postgres_pool(ds.id, params)
    conn = pool.connect()

    try:
        schema = schema_name or "public"
        if not _pg_table_exists(conn, schema, table_name):
            raise ValueError(f"Table not found: {schema}.{table_name}")

        payload = _pg_table_payload(db, conn, ds.id, schema, table_name)

        if column_name:
            for col in payload["columns"]:
                if col["name"] == column_name:
                    col["object_type"] = "column"
                    col["table"] = table_name
                    return col
            raise ValueError(f"Column not found: {target}")
        return payload
    finally:
        conn.close()


def _pg_table_exists(conn: Any, schema: str, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (schema, table_name),
    )
    return cur.fetchone() is not None


def _pg_table_payload(
    db: Session, conn: Any, datasource_id: str, schema: str, table_name: str
) -> dict[str, Any]:
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    catalog = _catalog_table(db, datasource_id, table_name)

    # columns
    cur.execute(
        "SELECT c.column_name, c.data_type, c.is_nullable, c.column_default, "
        "       pg_catalog.col_description("
        "         (c.table_schema||'.'||c.table_name)::regclass::oid, c.ordinal_position"
        "       ) AS col_comment, "
        "       CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END AS is_pk "
        "FROM information_schema.columns c "
        "LEFT JOIN ("
        "  SELECT ku.table_schema, ku.table_name, ku.column_name "
        "  FROM information_schema.table_constraints tc "
        "  JOIN information_schema.key_column_usage ku "
        "    ON tc.constraint_name = ku.constraint_name "
        "  WHERE tc.constraint_type = 'PRIMARY KEY'"
        ") pk "
        "  ON c.table_schema = pk.table_schema "
        " AND c.table_name = pk.table_name "
        " AND c.column_name = pk.column_name "
        "WHERE c.table_schema = %s AND c.table_name = %s "
        "ORDER BY c.ordinal_position",
        (schema, table_name),
    )
    columns: list[dict[str, Any]] = []
    pk_cols: list[str] = []
    for row in cur.fetchall():
        name = str(row["column_name"])
        is_pk = bool(row["is_pk"])
        if is_pk:
            pk_cols.append(name)
        columns.append({
            "name": name,
            "type": str(row["data_type"]),
            "nullable": str(row["is_nullable"]).upper() == "YES",
            "default": row["column_default"],
            "primary_key": is_pk,
            "foreign_key": None,  # filled below
            "comment": str(row["col_comment"] or ""),
        })

    # FK out
    fks_out: list[dict[str, Any]] = []
    col_map = {c["name"]: c for c in columns}
    cur.execute(
        "SELECT kcu.column_name, ccu.table_name AS ref_table, ccu.column_name AS ref_column "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        "AND tc.table_schema = kcu.table_schema "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "AND tc.table_schema = ccu.table_schema "
        "WHERE tc.constraint_type = 'FOREIGN KEY' "
        "  AND tc.table_schema = %s AND tc.table_name = %s",
        (schema, table_name),
    )
    for row in cur.fetchall():
        col_name = str(row["column_name"])
        fk = {"table": str(row["ref_table"]), "column": str(row["ref_column"])}
        fks_out.append({"column": col_name, "references": fk})
        if col_name in col_map:
            col_map[col_name]["foreign_key"] = fk

    # FK in (reverse)
    fks_in: list[dict[str, Any]] = []
    cur.execute(
        "SELECT tc.table_name, kcu.column_name, ccu.column_name AS ref_column "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        "AND tc.table_schema = kcu.table_schema "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "AND tc.table_schema = ccu.table_schema "
        "WHERE tc.constraint_type = 'FOREIGN KEY' "
        "  AND tc.table_schema = %s AND ccu.table_name = %s",
        (schema, table_name),
    )
    for row in cur.fetchall():
        fks_in.append({
            "table": str(row["table_name"]),
            "column": str(row["column_name"]),
            "references": {"column": str(row["ref_column"])},
        })

    # indexes
    indexes: list[dict[str, Any]] = []
    try:
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = %s AND tablename = %s",
            (schema, table_name),
        )
        for row in cur.fetchall():
            indexes.append({
                "name": str(row["indexname"]),
                "definition": str(row["indexdef"]),
                "unique": "UNIQUE" in str(row["indexdef"]).upper(),
            })
    except Exception:
        pass

    # row estimate
    row_est = None
    try:
        cur.execute(
            "SELECT n_live_tup FROM pg_stat_user_tables "
            "WHERE schemaname = %s AND relname = %s",
            (schema, table_name),
        )
        est = cur.fetchone()
        if est:
            row_est = int(est["n_live_tup"])
    except Exception:
        pass

    # table comment
    table_comment = ""
    try:
        cur.execute(
            "SELECT obj_description(%s::regclass, 'pg_class')", (f"{schema}.{table_name}",)
        )
        tc = cur.fetchone()
        if tc:
            table_comment = str(tc[0] or "")
    except Exception:
        pass

    return {
        "object_type": "table",
        "name": table_name,
        "type": "table",
        "dialect": "postgresql",
        "comment": table_comment or (str(catalog.table_comment or "") if catalog else ""),
        "row_estimate": row_est,
        "columns": columns,
        "primary_key": pk_cols,
        "foreign_keys_out": fks_out,
        "foreign_keys_in": fks_in,
        "indexes": indexes,
        "source": "live",
    }
