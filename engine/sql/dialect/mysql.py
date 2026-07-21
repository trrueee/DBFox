from __future__ import annotations

import logging
import time
from typing import Any

import pymysql

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.errors import SQLExecutionError, SQLQueryCancelledError
from engine.query_registry import QUERY_REGISTRY
from engine.sql.result_limits import QUERY_TIMEOUT_MS
from engine.sql.row_serializer import _fetch_and_serialize, QueryExecutionResult


logger = logging.getLogger("dbfox.sql.executor")


def _execute_on_mysql_profiled(
    datasource_id: str,
    profile: ConnectionProfile,
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> QueryExecutionResult:
    """Execute approved SQL via the factory's server-enforced read-only scope."""

    factory = connection_factory or ConnectionFactory()
    t_conn_start = time.perf_counter()
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.QUERY,
        read_only=True,
    ) as conn:
        connect_ms = int((time.perf_counter() - t_conn_start) * 1000)
        if execution_id:
            QUERY_REGISTRY.register_mysql(
                execution_id,
                datasource_id,
                profile,
                int(conn.thread_id()),
            )

        try:
            with conn.cursor() as cursor:
                try:
                    cursor.execute("SET SESSION MAX_EXECUTION_TIME=%s", (timeout_ms,))
                except Exception as exc:
                    log_unexpected_exception(
                        logger,
                        operation=SafeLogOperation.SQL_MYSQL_TIMEOUT_ENFORCEMENT,
                        exc=exc,
                        fingerprint_subject=(
                            f"{datasource_id}\x00{safe_sql}\x00{timeout_ms}\x00{type(exc).__name__}\x00{exc}"
                        ),
                        level="warning",
                    )
                    raise SQLExecutionError("Unable to enforce the MySQL query timeout.") from exc

                t_exec_start = time.perf_counter()
                try:
                    cursor.execute(safe_sql)
                except pymysql.err.OperationalError as exc:
                    code = exc.args[0] if exc.args else None
                    if execution_id and QUERY_REGISTRY.is_cancelled(execution_id):
                        raise SQLQueryCancelledError("SQL query cancelled by user") from exc
                    if code in {1317, 3024}:
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


def _execute_on_mysql(
    profile: ConnectionProfile,
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
    *,
    connection_factory: ConnectionFactory | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int]:
    result = _execute_on_mysql_profiled(
        datasource_id,
        profile,
        safe_sql,
        timeout_ms,
        execution_id,
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
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"EXPLAIN {safe_sql}")
            raw_rows = cursor.fetchall()
            for row in raw_rows:
                q_type = row.get("type") or row.get("Type")
                q_key = row.get("key") or row.get("Key")
                q_rows = row.get("rows") or row.get("Rows")
                q_extra = row.get("Extra") or row.get("extra") or ""

                records.append({
                    "type": q_type,
                    "key": q_key,
                    "rows": q_rows,
                    "Extra": q_extra,
                })

                type_str = str(q_type).upper() if q_type is not None else ""
                key_str = str(q_key).upper() if q_key is not None else ""
                if type_str == "ALL":
                    warnings.append(f"表 {row.get('table') or ''} 检测到全表扫描 (Type=ALL)，建议针对过滤/连接字段创建索引。")
                if not q_key or key_str == "NULL":
                    warnings.append(f"表 {row.get('table') or ''} 未命中任何索引 (Key=NULL)，查询性能可能受限。")
    return records, warnings
