from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from typing import Any, Literal

from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose

BackendKind = Literal["sqlite", "duckdb", "mysql", "postgresql"]


@dataclass
class RunningQuery:
    execution_id: str
    datasource_id: str
    backend: BackendKind
    sqlite_connection: sqlite3.Connection | None = None
    duckdb_connection: Any = None
    mysql_thread_id: int | None = None
    mysql_profile: ConnectionProfile | None = None
    postgres_connection: Any = None
    cancel_requested: bool = False


class QueryRegistry:
    def __init__(self, *, connection_factory: ConnectionFactory | None = None) -> None:
        self._lock = threading.RLock()
        self._queries: dict[str, RunningQuery] = {}
        self._connection_factory = connection_factory or ConnectionFactory()

    def register_sqlite(
        self,
        execution_id: str,
        datasource_id: str,
        connection: sqlite3.Connection,
    ) -> None:
        with self._lock:
            existing = self._queries.get(execution_id)
            self._queries[execution_id] = RunningQuery(
                execution_id=execution_id,
                datasource_id=datasource_id,
                backend="sqlite",
                sqlite_connection=connection,
                cancel_requested=existing.cancel_requested if existing else False,
            )

    def register_postgres(
        self,
        execution_id: str,
        datasource_id: str,
        connection: Any,
    ) -> None:
        with self._lock:
            existing = self._queries.get(execution_id)
            self._queries[execution_id] = RunningQuery(
                execution_id=execution_id,
                datasource_id=datasource_id,
                backend="postgresql",
                postgres_connection=connection,
                cancel_requested=existing.cancel_requested if existing else False,
            )

    def register_duckdb(
        self,
        execution_id: str,
        datasource_id: str,
        connection: Any,
    ) -> None:
        with self._lock:
            existing = self._queries.get(execution_id)
            self._queries[execution_id] = RunningQuery(
                execution_id=execution_id,
                datasource_id=datasource_id,
                backend="duckdb",
                duckdb_connection=connection,
                cancel_requested=existing.cancel_requested if existing else False,
            )

    def register_mysql(
        self,
        execution_id: str,
        datasource_id: str,
        profile: ConnectionProfile,
        thread_id: int,
    ) -> None:
        with self._lock:
            existing = self._queries.get(execution_id)
            self._queries[execution_id] = RunningQuery(
                execution_id=execution_id,
                datasource_id=datasource_id,
                backend="mysql",
                mysql_thread_id=thread_id,
                mysql_profile=profile,
                cancel_requested=existing.cancel_requested if existing else False,
            )

    def unregister(self, execution_id: str) -> None:
        with self._lock:
            self._queries.pop(execution_id, None)

    def is_cancelled(self, execution_id: str | None) -> bool:
        if not execution_id:
            return False
        with self._lock:
            return bool(self._queries.get(execution_id, None) and self._queries[execution_id].cancel_requested)

    def is_running(self, execution_id: str) -> bool:
        with self._lock:
            return execution_id in self._queries

    def cancel(self, execution_id: str) -> dict[str, Any]:
        with self._lock:
            query = self._queries.get(execution_id)
            if not query:
                return {
                    "success": False,
                    "cancelled": False,
                    "executionId": execution_id,
                    "message": "Query is not running or has already finished.",
                }

            query.cancel_requested = True
            backend = query.backend
            sqlite_connection = query.sqlite_connection
            duckdb_connection = query.duckdb_connection
            mysql_thread_id = query.mysql_thread_id
            mysql_profile = query.mysql_profile
            postgres_connection = query.postgres_connection

        if backend == "sqlite" and sqlite_connection is not None:
            sqlite_connection.interrupt()
            return {
                "success": True,
                "cancelled": True,
                "executionId": execution_id,
                "message": "SQLite query interruption requested.",
            }

        if backend == "duckdb" and duckdb_connection is not None:
            try:
                duckdb_connection.interrupt()
                return {
                    "success": True,
                    "cancelled": True,
                    "executionId": execution_id,
                    "message": "DuckDB query interruption requested.",
                }
            except Exception:
                return {
                    "success": False,
                    "cancelled": False,
                    "executionId": execution_id,
                    "message": fixed_error_message(FixedErrorCode.QUERY_CANCELLATION_FAILED),
                }

        if backend == "postgresql" and postgres_connection is not None:
            try:
                postgres_connection.cancel()
                return {
                    "success": True,
                    "cancelled": True,
                    "executionId": execution_id,
                    "message": "PostgreSQL query cancellation requested.",
                }
            except Exception:
                return {
                    "success": False,
                    "cancelled": False,
                    "executionId": execution_id,
                    "message": fixed_error_message(FixedErrorCode.QUERY_CANCELLATION_FAILED),
                }

        if backend == "mysql" and mysql_thread_id is not None and mysql_profile is not None:
            try:
                self._kill_mysql_query(mysql_profile, mysql_thread_id)
                return {
                    "success": True,
                    "cancelled": True,
                    "executionId": execution_id,
                    "message": "MySQL KILL QUERY requested.",
                }
            except Exception:
                return {
                    "success": False,
                    "cancelled": False,
                    "executionId": execution_id,
                    "message": fixed_error_message(FixedErrorCode.QUERY_CANCELLATION_FAILED),
                }

        return {
            "success": False,
            "cancelled": False,
            "executionId": execution_id,
            "message": "Running query backend is not cancellable yet.",
        }

    def _kill_mysql_query(self, profile: ConnectionProfile, thread_id: int) -> None:
        """Open a dedicated cancellation connection without retaining a password."""
        with self._connection_factory.connection_scope(
            profile,
            purpose=ConnectionPurpose.QUERY,
            read_only=False,
            pooled=False,
        ) as killer:
            with killer.cursor() as cursor:
                cursor.execute("KILL QUERY %s", (thread_id,))


QUERY_REGISTRY = QueryRegistry()
