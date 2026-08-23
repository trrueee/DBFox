"""Credential-brokered direct database connections owned by dbfox.data."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
import sqlite3
import threading
import time
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

from .connection_primitives import (
    existing_regular_file,
    network_driver_params,
    open_network_connection,
)
from .contracts import DatabaseHandle
from .sql.dry_run_contracts import DryRunResult, classify_dry_run_error
from .sql.bound_parameters import render_dbapi_sql
from .sql.readonly_query import ReadonlyQueryError, parse_single_readonly_query
from .sql.result_limits import QUERY_TIMEOUT_MS
from .sql.row_serializer import (
    QueryExecutionResult,
    _fetch_and_serialize,
)


CredentialGetter = Callable[[str, str], str | None]


class DataConnectionBoundary:
    """Open short-lived connections without exposing secrets to tool code.

    Pooling and SSH are deliberately absent from this first System DLC cutover:
    a profile that requests an unsupported transport fails closed instead of
    retrying against a less secure endpoint.
    """

    def __init__(self, credential_getter: CredentialGetter) -> None:
        self._credential_getter = credential_getter
        self._active_lock = threading.RLock()
        self._active: dict[str, tuple[str, Any] | None] = {}
        self._cancel_requested: set[str] = set()

    def cancel(self, invocation_id: str) -> None:
        """Interrupt only the connection owned by one Tool invocation."""

        normalized = str(invocation_id).strip()
        if not normalized:
            return
        with self._active_lock:
            self._cancel_requested.add(normalized)
            active = self._active.get(normalized)
        if active is None:
            return
        provider, connection = active
        try:
            if provider == "sqlite":
                connection.interrupt()
            elif provider == "postgresql":
                connection.cancel()
            else:
                connection.close()
        except Exception:
            return

    def _reserve(self, invocation_id: str) -> str:
        normalized = str(invocation_id).strip()
        if not normalized:
            raise RuntimeError("Database execution requires an invocation identity.")
        with self._active_lock:
            if normalized in self._active:
                raise RuntimeError("Database invocation is already executing.")
            self._active[normalized] = None
        return normalized

    def _attach(self, invocation_id: str, provider: str, connection: Any) -> None:
        with self._active_lock:
            self._active[invocation_id] = (provider, connection)
            cancelled = invocation_id in self._cancel_requested
        if cancelled:
            self.cancel(invocation_id)
            try:
                connection.close()
            except Exception:
                pass
            raise RuntimeError("Database execution was cancelled.")

    def _is_cancelled(
        self,
        invocation_id: str,
        cancellation_probe: Callable[[], bool] | None,
    ) -> bool:
        with self._active_lock:
            requested = invocation_id in self._cancel_requested
        return requested or bool(cancellation_probe and cancellation_probe())

    def _release(self, invocation_id: str) -> None:
        with self._active_lock:
            self._active.pop(invocation_id, None)
            self._cancel_requested.discard(invocation_id)

    def explain(self, handle: DatabaseHandle, sql: str) -> DryRunResult:
        dialect = handle.profile.provider
        try:
            parse_single_readonly_query(sql, dialect)
        except ReadonlyQueryError as exc:
            return DryRunResult(
                ok=False,
                blocked_reason="syntax_error",
                message=str(exc),
            )

        if handle.profile.ssh_enabled:
            return DryRunResult(
                ok=False,
                blocked_reason="explain_unavailable",
                message="SSH database validation is not available in the Data System DLC yet.",
            )

        try:
            if dialect == "sqlite":
                self._explain_sqlite(handle, sql)
            elif dialect == "mysql":
                self._explain_mysql(handle, sql)
            elif dialect == "postgresql":
                self._explain_postgresql(handle, sql)
            else:
                return DryRunResult(
                    ok=False,
                    blocked_reason="explain_unavailable",
                    message="This database provider does not support EXPLAIN validation.",
                )
        except Exception as exc:
            reason = classify_dry_run_error(exc, dialect)
            return DryRunResult(
                ok=False,
                blocked_reason=reason,
                message=(
                    "SQL references unavailable database objects."
                    if reason == "schema_error"
                    else "SQL could not be validated by the database."
                    if reason == "syntax_error"
                    else "The database was unavailable for EXPLAIN validation."
                ),
            )
        return DryRunResult(ok=True)

    def execute_readonly(
        self,
        handle: DatabaseHandle,
        sql: str,
        *,
        invocation_id: str,
        cancellation_probe: Callable[[], bool] | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> QueryExecutionResult:
        """Execute one already-admitted query through a read-only transaction."""

        execution_id = self._reserve(invocation_id)
        try:
            dialect = handle.profile.provider
            parse_single_readonly_query(sql, dialect)
            executable_sql, bound_parameters = render_dbapi_sql(
                sql,
                dialect,
                parameters,
            )
            if handle.profile.ssh_enabled:
                raise RuntimeError(
                    "SSH database execution is not available in the Data System DLC yet."
                )
            if dialect == "sqlite":
                return self._execute_sqlite(
                    handle,
                    executable_sql,
                    execution_id,
                    cancellation_probe,
                    bound_parameters,
                )
            if dialect == "mysql":
                return self._execute_mysql(
                    handle,
                    executable_sql,
                    execution_id,
                    bound_parameters,
                )
            if dialect == "postgresql":
                return self._execute_postgresql(
                    handle,
                    executable_sql,
                    execution_id,
                    bound_parameters,
                )
        except Exception as exc:
            raise RuntimeError("Read-only database execution failed.") from exc
        finally:
            self._release(execution_id)
        raise RuntimeError("This database provider does not support read execution.")

    @contextmanager
    def reflection_connection(
        self,
        handle: DatabaseHandle,
        *,
        invocation_id: str,
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> Iterator[Connection]:
        """Yield a short-lived SQLAlchemy connection for official Inspector APIs."""

        execution_id = self._reserve(invocation_id)
        engine = None
        try:
            if handle.profile.ssh_enabled:
                raise RuntimeError(
                    "SSH catalog reflection is not available in the Data System DLC yet."
                )
            dialect = handle.profile.provider

            def creator() -> Any:
                raw: Any
                if self._is_cancelled(execution_id, cancellation_probe):
                    raise RuntimeError("Database catalog reflection was cancelled.")
                if dialect == "sqlite":
                    path = existing_regular_file(
                        handle.database.database_name,
                        label="SQLite",
                    )
                    raw = sqlite3.connect(
                        path.as_uri() + "?mode=ro",
                        timeout=5,
                        uri=True,
                    )
                    raw.execute("PRAGMA query_only = ON")
                    raw.set_progress_handler(
                        lambda: 1
                        if self._is_cancelled(execution_id, cancellation_probe)
                        else 0,
                        1_000,
                    )
                else:
                    host, port, username = self._require_network_fields(handle)
                    params = network_driver_params(
                        provider=dialect,
                        host=host,
                        port=port,
                        username=username,
                        database=handle.database.database_name,
                        config=handle.profile,
                    )
                    params["password"] = self._network_password(handle)
                    params["autocommit"] = False
                    raw = open_network_connection(dialect, params)
                    if dialect == "postgresql":
                        raw.set_session(readonly=True, autocommit=False)
                    elif dialect == "mysql":
                        cursor = raw.cursor()
                        try:
                            cursor.execute("SET SESSION TRANSACTION READ ONLY")
                        finally:
                            cursor.close()
                self._attach(execution_id, dialect, raw)
                return raw

            driver = {
                "sqlite": "sqlite+pysqlite://",
                "mysql": "mysql+pymysql://",
                "postgresql": "postgresql+psycopg2://",
            }.get(dialect)
            if driver is None:
                raise RuntimeError("This database provider does not support catalog reflection.")
            engine = create_engine(driver, creator=creator, poolclass=NullPool)
            with engine.connect() as connection:
                yield connection
        finally:
            if engine is not None:
                engine.dispose()
            self._release(execution_id)

    def _execute_sqlite(
        self,
        handle: DatabaseHandle,
        sql: str,
        invocation_id: str,
        cancellation_probe: Callable[[], bool] | None,
        parameters: Mapping[str, Any],
    ) -> QueryExecutionResult:
        started = time.perf_counter()
        path = existing_regular_file(handle.database.database_name, label="SQLite")
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", timeout=5, uri=True)
        connect_ms = int((time.perf_counter() - started) * 1_000)
        self._attach(invocation_id, "sqlite", connection)
        deadline = time.monotonic() + QUERY_TIMEOUT_MS / 1_000
        connection.row_factory = sqlite3.Row
        connection.set_progress_handler(
            lambda: 1
            if time.monotonic() >= deadline
            or self._is_cancelled(invocation_id, cancellation_probe)
            else 0,
            1_000,
        )
        try:
            connection.execute("PRAGMA query_only = ON")
            execute_started = time.perf_counter()
            cursor = connection.execute(sql, parameters)
            execute_ms = int((time.perf_counter() - execute_started) * 1_000)
            fetched = _fetch_and_serialize(cursor)
            return QueryExecutionResult.from_fetch_result(
                fetched,
                connect_ms=connect_ms,
                execute_ms=execute_ms,
            )
        finally:
            connection.close()

    @staticmethod
    def _row_mapper(cursor: Any) -> Callable[[Any], dict[str, Any]]:
        columns = [str(column[0]) for column in cursor.description or ()]
        return lambda row: {
            column: row[index]
            for index, column in enumerate(columns)
        }

    def _execute_mysql(
        self,
        handle: DatabaseHandle,
        sql: str,
        invocation_id: str,
        parameters: Mapping[str, Any],
    ) -> QueryExecutionResult:
        host, port, username = self._require_network_fields(handle)
        params = network_driver_params(
            provider="mysql",
            host=host,
            port=port,
            username=username,
            database=handle.database.database_name,
            config=handle.profile,
        )
        params["password"] = self._network_password(handle)
        params["autocommit"] = False
        started = time.perf_counter()
        connection = open_network_connection("mysql", params)
        connect_ms = int((time.perf_counter() - started) * 1_000)
        self._attach(invocation_id, "mysql", connection)
        try:
            with connection.cursor() as cursor:
                cursor.execute("START TRANSACTION READ ONLY")
                execute_started = time.perf_counter()
                cursor.execute(sql, parameters)
                execute_ms = int((time.perf_counter() - execute_started) * 1_000)
                fetched = _fetch_and_serialize(
                    cursor,
                    row_mapper=self._row_mapper(cursor),
                )
                return QueryExecutionResult.from_fetch_result(
                    fetched,
                    connect_ms=connect_ms,
                    execute_ms=execute_ms,
                )
        finally:
            try:
                connection.rollback()
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass

    def _execute_postgresql(
        self,
        handle: DatabaseHandle,
        sql: str,
        invocation_id: str,
        parameters: Mapping[str, Any],
    ) -> QueryExecutionResult:
        host, port, username = self._require_network_fields(handle)
        params = network_driver_params(
            provider="postgresql",
            host=host,
            port=port,
            username=username,
            database=handle.database.database_name,
            config=handle.profile,
        )
        params["password"] = self._network_password(handle)
        started = time.perf_counter()
        connection = open_network_connection("postgresql", params)
        connect_ms = int((time.perf_counter() - started) * 1_000)
        self._attach(invocation_id, "postgresql", connection)
        try:
            connection.set_session(readonly=True, autocommit=False)
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = %s", (QUERY_TIMEOUT_MS,))
                execute_started = time.perf_counter()
                cursor.execute(sql, parameters)
                execute_ms = int((time.perf_counter() - execute_started) * 1_000)
                fetched = _fetch_and_serialize(
                    cursor,
                    row_mapper=self._row_mapper(cursor),
                )
                return QueryExecutionResult.from_fetch_result(
                    fetched,
                    connect_ms=connect_ms,
                    execute_ms=execute_ms,
                )
        finally:
            try:
                connection.rollback()
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass

    def _explain_sqlite(self, handle: DatabaseHandle, sql: str) -> None:
        path = existing_regular_file(
            handle.database.database_name,
            label="SQLite",
        )
        uri = path.as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, timeout=5, uri=True)
        try:
            connection.execute(f"EXPLAIN QUERY PLAN {sql}").fetchone()
        finally:
            connection.close()

    def _network_password(self, handle: DatabaseHandle) -> str:
        credential_ref = str(handle.profile.password_credential_ref or "").strip()
        if not credential_ref:
            raise RuntimeError("Database password credential is unavailable")
        secret = self._credential_getter(credential_ref, "datasource_password")
        if not secret:
            raise RuntimeError("Database password credential is unavailable")
        return secret

    @staticmethod
    def _require_network_fields(handle: DatabaseHandle) -> tuple[str, int, str]:
        profile = handle.profile
        if not profile.host or not profile.port or not profile.username:
            raise RuntimeError("Network database profile is incomplete")
        return profile.host, profile.port, profile.username

    def _explain_mysql(self, handle: DatabaseHandle, sql: str) -> None:
        host, port, username = self._require_network_fields(handle)
        params = network_driver_params(
            provider="mysql",
            host=host,
            port=port,
            username=username,
            database=handle.database.database_name,
            config=handle.profile,
        )
        params["password"] = self._network_password(handle)
        params["autocommit"] = False
        connection = open_network_connection("mysql", params)
        try:
            with connection.cursor() as cursor:
                cursor.execute("START TRANSACTION READ ONLY")
                cursor.execute(f"EXPLAIN {sql}")
                cursor.fetchone()
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()

    def _explain_postgresql(self, handle: DatabaseHandle, sql: str) -> None:
        host, port, username = self._require_network_fields(handle)
        params = network_driver_params(
            provider="postgresql",
            host=host,
            port=port,
            username=username,
            database=handle.database.database_name,
            config=handle.profile,
        )
        params["password"] = self._network_password(handle)
        connection = open_network_connection("postgresql", params)
        try:
            connection.set_session(readonly=True, autocommit=False)
            with connection.cursor() as cursor:
                cursor.execute(f"EXPLAIN (FORMAT JSON) {sql}")
                cursor.fetchone()
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()
