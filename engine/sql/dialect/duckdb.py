from __future__ import annotations

import time
from typing import Any

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.errors import SQLQueryCancelledError
from engine.query_registry import QUERY_REGISTRY
from engine.sql.result_limits import QUERY_TIMEOUT_MS
from engine.sql.row_serializer import _fetch_and_serialize, QueryExecutionResult


def _execute_on_duckdb_profiled(
    datasource_id: str,
    profile: ConnectionProfile,
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> QueryExecutionResult:
    """Execute a guarded DuckDB query on a factory-owned read-only connection.

    DuckDB exposes connection interruption but does not provide a portable
    server-side statement-timeout setting.  The TrustGate limit remains in
    force and cancellation uses the registered connection's ``interrupt`` API.
    """

    del timeout_ms
    factory = connection_factory or ConnectionFactory()
    t_conn_start = time.perf_counter()
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.QUERY,
        read_only=True,
    ) as conn:
        connect_ms = int((time.perf_counter() - t_conn_start) * 1000)
        if execution_id:
            QUERY_REGISTRY.register_duckdb(execution_id, datasource_id, conn)
        cursor: Any | None = None
        try:
            cursor = conn.cursor()
            t_exec_start = time.perf_counter()
            try:
                cursor.execute(safe_sql)
            except Exception as exc:
                if execution_id and QUERY_REGISTRY.is_cancelled(execution_id):
                    raise SQLQueryCancelledError("SQL query cancelled by user") from exc
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
            if cursor is not None:
                cursor.close()


def explain(
    profile: ConnectionProfile,
    safe_sql: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    factory = connection_factory or ConnectionFactory()
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.EXPLAIN,
        read_only=True,
    ) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(f"EXPLAIN {safe_sql}")
            columns = [item[0] for item in cursor.description or []]
            records = [
                {column: value for column, value in zip(columns, row)}
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()
    warnings = [
        "查询计划包含顺序扫描，建议检查过滤字段或连接字段上的索引。"
        for record in records
        if "SEQ_SCAN" in " ".join(str(value) for value in record.values()).upper()
    ]
    return records, warnings
