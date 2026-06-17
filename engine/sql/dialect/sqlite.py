from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

from engine.errors import SQLQueryCancelledError
from engine.query_registry import QUERY_REGISTRY
from engine.sql.row_serializer import (
    _fetch_and_serialize,
    QUERY_TIMEOUT_MS,
)

logger = logging.getLogger("dbfox.sql.executor")


def _execute_on_sqlite_profiled(
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
    sqlite_path: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int, int, int]:
    """Execute a safe SQL query on the SQLite database, returning timing breakdown."""
    db_path = sqlite_path
    if not db_path:
        raise ValueError("SQLite database path is required for query execution")

    t_conn_start = time.perf_counter()
    conn = sqlite3.connect(db_path)
    connect_ms = int((time.perf_counter() - t_conn_start) * 1000)

    conn.row_factory = sqlite3.Row
    deadline = time.monotonic() + (timeout_ms / 1000)
    timed_out = False

    def abort_when_timed_out() -> int:
        nonlocal timed_out
        if time.monotonic() > deadline:
            timed_out = True
            return 1
        return 0

    try:
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.set_progress_handler(abort_when_timed_out, 1000)
        if execution_id:
            QUERY_REGISTRY.register_sqlite(execution_id, datasource_id, conn)
        cursor = conn.cursor()

        t_exec_start = time.perf_counter()
        try:
            cursor.execute(safe_sql)
        except sqlite3.OperationalError as exc:
            if execution_id and QUERY_REGISTRY.is_cancelled(execution_id):
                raise SQLQueryCancelledError("SQL query cancelled by user") from exc
            if timed_out:
                raise TimeoutError(f"Query timed out after {timeout_ms} ms") from exc
            raise
        execute_ms = int((time.perf_counter() - t_exec_start) * 1000)

        rows, columns, truncated, response_bytes, fetch_ms, serialize_ms = _fetch_and_serialize(cursor)

        return rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms
    finally:
        if execution_id:
            QUERY_REGISTRY.unregister(execution_id)
        conn.set_progress_handler(None, 0)
        conn.close()


def _execute_on_sqlite(
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
    sqlite_path: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int]:
    rows, columns, truncated, response_bytes, _, _, _, _ = _execute_on_sqlite_profiled(
        safe_sql, timeout_ms, execution_id, datasource_id, sqlite_path
    )
    return rows, columns, truncated, response_bytes
