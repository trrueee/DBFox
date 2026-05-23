from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from typing import Any, Literal

import pymysql

BackendKind = Literal["sqlite", "mysql"]


@dataclass
class RunningQuery:
    execution_id: str
    datasource_id: str
    backend: BackendKind
    sqlite_connection: sqlite3.Connection | None = None
    mysql_thread_id: int | None = None
    mysql_params: dict[str, Any] | None = None
    cancel_requested: bool = False


class QueryRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._queries: dict[str, RunningQuery] = {}

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

    def register_mysql(
        self,
        execution_id: str,
        datasource_id: str,
        params: dict[str, Any],
        thread_id: int,
    ) -> None:
        safe_params = dict(params)
        with self._lock:
            existing = self._queries.get(execution_id)
            self._queries[execution_id] = RunningQuery(
                execution_id=execution_id,
                datasource_id=datasource_id,
                backend="mysql",
                mysql_thread_id=thread_id,
                mysql_params=safe_params,
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
            mysql_thread_id = query.mysql_thread_id
            mysql_params = dict(query.mysql_params or {})

        if backend == "sqlite" and sqlite_connection is not None:
            sqlite_connection.interrupt()
            return {
                "success": True,
                "cancelled": True,
                "executionId": execution_id,
                "message": "SQLite query interruption requested.",
            }

        if backend == "mysql" and mysql_thread_id is not None and mysql_params:
            try:
                self._kill_mysql_query(mysql_params, mysql_thread_id)
                return {
                    "success": True,
                    "cancelled": True,
                    "executionId": execution_id,
                    "message": "MySQL KILL QUERY requested.",
                }
            except Exception as exc:
                return {
                    "success": False,
                    "cancelled": False,
                    "executionId": execution_id,
                    "message": f"Failed to issue MySQL KILL QUERY: {exc}",
                }

        return {
            "success": False,
            "cancelled": False,
            "executionId": execution_id,
            "message": "Running query backend is not cancellable yet.",
        }

    def _kill_mysql_query(self, params: dict[str, Any], thread_id: int) -> None:
        params = dict(params)
        killer = pymysql.connect(**params)
        try:
            with killer.cursor() as cursor:
                cursor.execute(f"KILL QUERY {int(thread_id)}")
        finally:
            killer.close()


QUERY_REGISTRY = QueryRegistry()
