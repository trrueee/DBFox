from __future__ import annotations

import logging
import time
from typing import Any

import pymysql

from engine.errors import SQLQueryCancelledError
from engine.query_registry import QUERY_REGISTRY
from engine.sql.pool_manager import get_mysql_pool, _ping_mysql_connection
from engine.sql.row_serializer import (
    _fetch_and_serialize,
    QUERY_TIMEOUT_MS,
)

logger = logging.getLogger("dbfox.sql.executor")


def _execute_on_mysql_profiled(
    datasource_id: str,
    params: dict[str, Any],
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int, int, int]:
    """Execute a safe SQL query on a real MySQL database via PyMySQL, returning timing breakdown."""
    t_conn_start = time.perf_counter()
    pool = get_mysql_pool(datasource_id, params)
    conn_proxy: Any = pool.connect()
    connect_ms = int((time.perf_counter() - t_conn_start) * 1000)

    try:
        raw_conn = _ping_mysql_connection(conn_proxy)
        if execution_id:
            QUERY_REGISTRY.register_mysql(
                execution_id,
                datasource_id,
                params,
                int(raw_conn.thread_id()),
            )

        with conn_proxy.cursor() as cursor:
            try:
                cursor.execute("SET SESSION MAX_EXECUTION_TIME=%s", (timeout_ms,))
            except Exception as exc:
                logger.warning("Failed to set MySQL MAX_EXECUTION_TIME: %s", exc)

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

            rows, columns, truncated, response_bytes, fetch_ms, serialize_ms = _fetch_and_serialize(cursor)

            return rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms
    finally:
        if execution_id:
            QUERY_REGISTRY.unregister(execution_id)
        conn_proxy.close()


def _execute_on_mysql(
    params: dict[str, Any],
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
) -> tuple[list[dict[str, Any]], list[str], bool, int]:
    rows, columns, truncated, response_bytes, _, _, _, _ = _execute_on_mysql_profiled(
        datasource_id, params, safe_sql, timeout_ms, execution_id
    )
    return rows, columns, truncated, response_bytes


def explain(datasource_id: str, conn_params: dict[str, Any], safe_sql: str) -> tuple[list[dict[str, Any]], list[str]]:
    pool = get_mysql_pool(datasource_id, conn_params)
    conn_proxy: Any = pool.connect()
    records = []
    warnings = []
    try:
        _ping_mysql_connection(conn_proxy)
        with conn_proxy.cursor() as cursor:
            cursor.execute(f"EXPLAIN {safe_sql}")
            raw_rows = cursor.fetchall()
            for r in raw_rows:
                q_type = r.get("type") or r.get("Type")
                q_key = r.get("key") or r.get("Key")
                q_rows = r.get("rows") or r.get("Rows")
                q_extra = r.get("Extra") or r.get("extra") or ""
                
                records.append({
                    "type": q_type,
                    "key": q_key,
                    "rows": q_rows,
                    "Extra": q_extra
                })
                
                type_str = str(q_type).upper() if q_type is not None else ""
                key_str = str(q_key).upper() if q_key is not None else ""
                
                if type_str == "ALL":
                    warnings.append(f"表 {r.get('table') or ''} 检测到全表扫描 (Type=ALL)，建议针对过滤/连接字段创建索引。")
                if not q_key or key_str == "NULL":
                    warnings.append(f"表 {r.get('table') or ''} 未命中任何索引 (Key=NULL)，查询性能可能受限。")
    finally:
        conn_proxy.close()
    return records, warnings
