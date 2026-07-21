from __future__ import annotations

import time
from typing import Any

import sqlite3

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.errors import SQLQueryCancelledError
from engine.query_registry import QUERY_REGISTRY
from engine.sql.result_limits import QUERY_TIMEOUT_MS
from engine.sql.row_serializer import _fetch_and_serialize, QueryExecutionResult


def _execute_on_sqlite_profiled(
    safe_sql: str,
    *,
    profile: ConnectionProfile,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
    connection_factory: ConnectionFactory | None = None,
) -> QueryExecutionResult:
    """Execute read-only SQLite SQL through the shared connection factory."""

    factory = connection_factory or ConnectionFactory()
    t_conn_start = time.perf_counter()
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.QUERY,
        read_only=True,
        sqlite_row_factory=sqlite3.Row,
    ) as conn:
        connect_ms = int((time.perf_counter() - t_conn_start) * 1000)
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

            serialized = _fetch_and_serialize(cursor)
            return QueryExecutionResult.from_fetch_result(
                serialized,
                connect_ms=connect_ms,
                execute_ms=execute_ms,
            )
        finally:
            if execution_id:
                QUERY_REGISTRY.unregister(execution_id)
            conn.set_progress_handler(None, 0)


def _execute_on_sqlite(
    safe_sql: str,
    *,
    profile: ConnectionProfile,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
    connection_factory: ConnectionFactory | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int]:
    result = _execute_on_sqlite_profiled(
        safe_sql,
        profile=profile,
        timeout_ms=timeout_ms,
        execution_id=execution_id,
        datasource_id=datasource_id,
        connection_factory=connection_factory,
    )
    return result.rows, result.columns, result.truncated, result.response_bytes


def explain(
    profile: ConnectionProfile,
    safe_sql: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    factory = connection_factory or ConnectionFactory()
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.EXPLAIN,
        read_only=True,
        sqlite_row_factory=sqlite3.Row,
    ) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(f"EXPLAIN QUERY PLAN {safe_sql}")
            raw_rows = cursor.fetchall()
            for row in raw_rows:
                detail = str(row["detail"])
                is_scan = "SCAN" in detail.upper()
                is_search = "SEARCH" in detail.upper()

                q_type = "ALL" if is_scan else "RANGE" if is_search else "INDEX"
                q_key = None
                if "USING INDEX" in detail.upper():
                    parts = detail.split("USING INDEX")
                    if len(parts) > 1:
                        q_key = parts[1].strip().split()[0]

                records.append({
                    "type": q_type,
                    "key": q_key,
                    "rows": None,
                    "Extra": detail,
                })

                if q_type == "ALL":
                    warnings.append("检测到全表扫描 (Type=ALL)，建议在过滤字段上建立索引")
                if q_key is None or q_key == "NULL":
                    warnings.append("未命中任何索引 (Key=NULL)，查询性能可能受限")
        finally:
            cursor.close()
    return records, warnings
