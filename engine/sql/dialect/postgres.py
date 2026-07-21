from __future__ import annotations

import logging
import time
from typing import Any

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.errors import SQLExecutionError, SQLQueryCancelledError
from engine.query_registry import QUERY_REGISTRY
from engine.sql.result_limits import QUERY_TIMEOUT_MS
from engine.sql.row_serializer import _fetch_and_serialize, QueryExecutionResult


logger = logging.getLogger("dbfox.sql.executor")


def _execute_on_postgres_profiled(
    datasource_id: str,
    profile: ConnectionProfile,
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> QueryExecutionResult:
    """Execute approved SQL through a native read-only factory scope."""

    factory = connection_factory or ConnectionFactory()
    t_conn_start = time.perf_counter()
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.QUERY,
        read_only=True,
    ) as conn:
        connect_ms = int((time.perf_counter() - t_conn_start) * 1000)
        if execution_id:
            QUERY_REGISTRY.register_postgres(execution_id, datasource_id, conn)

        try:
            with conn.cursor() as cursor:
                try:
                    cursor.execute("SET LOCAL statement_timeout = %s", (timeout_ms,))
                except Exception as exc:
                    log_unexpected_exception(
                        logger,
                        operation=SafeLogOperation.SQL_POSTGRES_TIMEOUT_ENFORCEMENT,
                        exc=exc,
                        fingerprint_subject=(
                            f"{datasource_id}\x00{safe_sql}\x00{timeout_ms}\x00{type(exc).__name__}\x00{exc}"
                        ),
                        level="warning",
                    )
                    raise SQLExecutionError("Unable to enforce the PostgreSQL query timeout.") from exc

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
                serialized = _fetch_and_serialize(
                    cursor,
                    row_mapper=lambda row, _columns=pg_columns: dict(zip(_columns, row)) if _columns else row,
                )
                return QueryExecutionResult.from_fetch_result(
                    serialized,
                    connect_ms=connect_ms,
                    execute_ms=execute_ms,
                )
        finally:
            if execution_id:
                QUERY_REGISTRY.unregister(execution_id)
