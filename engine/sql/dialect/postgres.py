from __future__ import annotations

import logging
import time
from typing import Any

from engine.errors import SQLQueryCancelledError
from engine.query_registry import QUERY_REGISTRY
from engine.sql.pool_manager import get_postgres_pool
from engine.sql.row_serializer import (
    _fetch_and_serialize,
    QUERY_TIMEOUT_MS,
)

logger = logging.getLogger("dbfox.sql.executor")


def _execute_on_postgres_profiled(
    datasource_id: str,
    params: dict[str, Any],
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int, int, int]:
    """Execute a safe SQL query on a real PostgreSQL database, returning timing breakdown."""
    t_conn_start = time.perf_counter()
    pool = get_postgres_pool(datasource_id, params)
    conn_proxy: Any = pool.connect()
    connect_ms = int((time.perf_counter() - t_conn_start) * 1000)

    try:
        raw_conn = conn_proxy.connection if hasattr(conn_proxy, "connection") else conn_proxy
        if execution_id:
            QUERY_REGISTRY.register_postgres(
                execution_id,
                datasource_id,
                raw_conn,
            )

        with conn_proxy.cursor() as cursor:
            try:
                cursor.execute(f"SET statement_timeout = {timeout_ms}")
            except Exception as exc:
                logger.warning("Failed to set Postgres statement timeout: %s", exc)

            t_exec_start = time.perf_counter()
            try:
                cursor.execute(safe_sql)
            except Exception as exc:
                if execution_id and QUERY_REGISTRY.is_cancelled(execution_id):
                    raise SQLQueryCancelledError("SQL query cancelled by user") from exc

                pgcode = getattr(exc, "pgcode", None)
                if pgcode == "57014":
                    raise TimeoutError(f"Query timed out after {timeout_ms} ms") from exc
                raise
            execute_ms = int((time.perf_counter() - t_exec_start) * 1000)

            pg_columns = [col[0] for col in cursor.description] if cursor.description else []
            mapped_rows, columns_raw, truncated, response_bytes, fetch_ms, serialize_ms = _fetch_and_serialize(
                cursor, row_mapper=lambda r, _c=pg_columns: dict(zip(_c, r)) if _c else r,
            )

            return mapped_rows, columns_raw, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms
    finally:
        if execution_id:
            QUERY_REGISTRY.unregister(execution_id)
        conn_proxy.close()
