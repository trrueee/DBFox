from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from collections.abc import Iterator
from threading import Timer
from time import monotonic
from typing import Any

from sqlalchemy.orm import Session

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.datasource import datasource_connection_dict
from engine.errors import GuardrailValidationError, SQLExecutionError, SQLQueryTimeoutError
from engine.models import DataSource
from engine.policy.sensitivity import _SENSITIVE_FALLBACK, load_sensitivity, redact_row
from engine.sql.row_serializer import _serialize_value
from engine.sql.safety_gate import _resolve_execution_safety_decision
from engine.sql.trust_gate import ExecutionSafetyDecision


DEFAULT_EXPORT_MAX_ROWS = 100_000
DEFAULT_EXPORT_TIMEOUT_MS = 30_000
MAX_EXPORT_TIMEOUT_MS = 300_000


def export_max_rows_from_env() -> int:
    raw = os.environ.get("DBFOX_EXPORT_MAX_ROWS")
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_EXPORT_MAX_ROWS


def export_timeout_ms_from_env() -> int:
    raw = os.environ.get("DBFOX_EXPORT_TIMEOUT_MS")
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return min(parsed, MAX_EXPORT_TIMEOUT_MS)
        except ValueError:
            pass
    return DEFAULT_EXPORT_TIMEOUT_MS


class _ExportDeadline:
    """One monotonic deadline shared by execution and every streamed fetch."""

    def __init__(self, timeout_ms: int) -> None:
        if timeout_ms <= 0:
            raise ValueError("Streaming export timeout must be positive.")
        self.timeout_ms = timeout_ms
        self._expires_at = monotonic() + timeout_ms / 1000
        self._timed_out = False

    @property
    def expired(self) -> bool:
        return self._timed_out or monotonic() >= self._expires_at

    def trigger(self) -> None:
        """Record a watchdog interrupt even on coarse-resolution system clocks."""
        self._timed_out = True

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self._expires_at - monotonic())

    def check(self) -> None:
        if self.expired:
            raise SQLQueryTimeoutError("Streaming export timed out.")


def _configure_postgres_timeout(connection: Any, timeout_ms: int) -> None:
    """Apply a transaction-local PostgreSQL deadline before opening a cursor."""
    cursor: Any | None = None
    try:
        cursor = connection.cursor()
        cursor.execute("SET LOCAL statement_timeout = %s", (timeout_ms,))
    except Exception as exc:
        raise SQLExecutionError("Unable to enforce the streaming export timeout.") from exc
    finally:
        if cursor is not None:
            cursor.close()


def _configure_mysql_timeout(connection: Any, timeout_ms: int) -> None:
    """Apply MySQL's server-side SELECT deadline before export execution."""
    cursor: Any | None = None
    try:
        cursor = connection.cursor()
        cursor.execute("SET SESSION MAX_EXECUTION_TIME = %s", (timeout_ms,))
    except Exception as exc:
        raise SQLExecutionError("Unable to enforce the streaming export timeout.") from exc
    finally:
        if cursor is not None:
            cursor.close()


def _reset_mysql_timeout(connection: Any) -> None:
    """Do not leak an export-only timeout into a pooled connection's next use."""
    cursor: Any | None = None
    try:
        cursor = connection.cursor()
        cursor.execute("SET SESSION MAX_EXECUTION_TIME = 0")
    except Exception:
        # The connection is about to leave the export scope.  A reset failure
        # must not mask the original query result or reveal a driver message.
        return
    finally:
        if cursor is not None:
            cursor.close()


def _install_sqlite_progress_handler(connection: Any, deadline: _ExportDeadline):
    """Install a SQLite VM callback that aborts as soon as the deadline elapses."""
    setter = getattr(connection, "set_progress_handler", None)
    if not callable(setter):
        raise SQLExecutionError("Unable to enforce the streaming export timeout.")

    def abort_if_expired() -> int:
        return 1 if deadline.expired else 0

    setter(abort_if_expired, 1_000)

    def restore() -> None:
        setter(None, 0)

    return restore


@contextmanager
def _deadline_watchdog(connection: Any, deadline: _ExportDeadline) -> Iterator[None]:
    """Interrupt a blocking driver call when the monotonic export deadline expires."""
    interruptors = [
        getattr(connection, name, None)
        for name in ("interrupt", "cancel", "close")
    ]
    if not any(callable(interruptor) for interruptor in interruptors):
        raise SQLExecutionError("Unable to enforce the streaming export timeout.")

    def interrupt() -> None:
        deadline.trigger()
        for interruptor in interruptors:
            if not callable(interruptor):
                continue
            try:
                interruptor()
                return
            except Exception:
                continue

    timer = Timer(deadline.remaining_seconds, interrupt)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()


def _translate_deadline_error(deadline: _ExportDeadline, exc: Exception) -> None:
    if deadline.expired:
        raise SQLQueryTimeoutError("Streaming export timed out.") from exc
    raise exc


class StreamingQueryExecutor:
    """Stream an approved read-only result through the connection boundary."""

    def __init__(
        self,
        db: Session,
        *,
        max_rows: int | None = None,
        timeout_ms: int | None = None,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self.db = db
        self.max_rows = max_rows or export_max_rows_from_env()
        self.timeout_ms = timeout_ms if timeout_ms is not None else export_timeout_ms_from_env()
        if self.timeout_ms <= 0:
            raise ValueError("Streaming export timeout must be positive.")
        self.connection_factory = connection_factory or ConnectionFactory()

    def stream_rows(
        self,
        datasource_id: str,
        sql: str,
        decision: ExecutionSafetyDecision | dict[str, Any],
        chunk_size: int = 1000,
        timeout_ms: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        resolved = _resolve_execution_safety_decision(
            db=self.db,
            datasource_id=datasource_id,
            sql_str=sql,
            bypass_guardrail=False,
            safety_decision=decision,
            policy="export",
        )
        if not resolved.can_execute or not str(resolved.safe_sql or "").strip():
            raise GuardrailValidationError("Export SQL is blocked by safety rules.")

        ds = self.db.query(DataSource).filter(DataSource.id == datasource_id).first()
        if ds is None:
            raise ValueError("Data source not found")

        safe_sql = str(resolved.safe_sql or "").strip()
        sensitivity = self._load_sensitivity(datasource_id)
        profile = ConnectionProfile.from_mapping(datasource_connection_dict(ds))
        deadline = _ExportDeadline(timeout_ms if timeout_ms is not None else self.timeout_ms)
        if profile.dialect == "sqlite":
            yield from self._stream_sqlite(profile, safe_sql, chunk_size, sensitivity, deadline)
        elif profile.dialect == "duckdb":
            yield from self._stream_duckdb(profile, safe_sql, chunk_size, sensitivity, deadline)
        elif profile.dialect == "postgresql":
            yield from self._stream_postgres(profile, safe_sql, chunk_size, sensitivity, deadline)
        else:
            yield from self._stream_mysql(profile, safe_sql, chunk_size, sensitivity, deadline)

    def _load_sensitivity(self, datasource_id: str) -> Any:
        try:
            return load_sensitivity(self.db, datasource_id)
        except Exception:
            return _SENSITIVE_FALLBACK

    def _redact(self, row: dict[str, Any], sensitivity: Any) -> dict[str, Any]:
        try:
            return redact_row(row, sensitivity)
        except Exception:
            return redact_row(row, _SENSITIVE_FALLBACK)

    def _stream_sqlite(
        self,
        profile: ConnectionProfile,
        sql: str,
        chunk_size: int,
        sensitivity: Any,
        deadline: _ExportDeadline,
    ) -> Iterator[dict[str, Any]]:
        with self.connection_factory.connection_scope(
            profile,
            purpose=ConnectionPurpose.STREAMING_EXPORT,
            read_only=True,
        ) as conn:
            cursor: Any | None = None
            restore_progress = _install_sqlite_progress_handler(conn, deadline)
            try:
                with _deadline_watchdog(conn, deadline):
                    deadline.check()
                    cursor = conn.cursor()
                    cursor.execute(sql)
                    deadline.check()
                    yield from self._yield_rows(cursor, chunk_size, sensitivity, deadline)
            except SQLQueryTimeoutError:
                raise
            except Exception as exc:
                _translate_deadline_error(deadline, exc)
            finally:
                if cursor is not None:
                    cursor.close()
                restore_progress()

    def _stream_duckdb(
        self,
        profile: ConnectionProfile,
        sql: str,
        chunk_size: int,
        sensitivity: Any,
        deadline: _ExportDeadline,
    ) -> Iterator[dict[str, Any]]:
        with self.connection_factory.connection_scope(
            profile,
            purpose=ConnectionPurpose.STREAMING_EXPORT,
            read_only=True,
        ) as conn:
            cursor: Any | None = None
            try:
                with _deadline_watchdog(conn, deadline):
                    deadline.check()
                    cursor = conn.cursor()
                    cursor.execute(sql)
                    deadline.check()
                    yield from self._yield_rows(cursor, chunk_size, sensitivity, deadline)
            except SQLQueryTimeoutError:
                raise
            except Exception as exc:
                _translate_deadline_error(deadline, exc)
            finally:
                if cursor is not None:
                    cursor.close()

    def _stream_postgres(
        self,
        profile: ConnectionProfile,
        sql: str,
        chunk_size: int,
        sensitivity: Any,
        deadline: _ExportDeadline,
    ) -> Iterator[dict[str, Any]]:
        with self.connection_factory.connection_scope(
            profile,
            purpose=ConnectionPurpose.STREAMING_EXPORT,
            read_only=True,
        ) as conn:
            cursor: Any | None = None
            try:
                with _deadline_watchdog(conn, deadline):
                    deadline.check()
                    _configure_postgres_timeout(conn, deadline.timeout_ms)
                    cursor = conn.cursor(name=f"dbfox_export_{uuid.uuid4().hex}")
                    cursor.itersize = chunk_size
                    cursor.execute(sql)
                    deadline.check()
                    yield from self._yield_rows(cursor, chunk_size, sensitivity, deadline)
            except SQLQueryTimeoutError:
                raise
            except Exception as exc:
                _translate_deadline_error(deadline, exc)
            finally:
                if cursor is not None:
                    cursor.close()

    def _stream_mysql(
        self,
        profile: ConnectionProfile,
        sql: str,
        chunk_size: int,
        sensitivity: Any,
        deadline: _ExportDeadline,
    ) -> Iterator[dict[str, Any]]:
        import pymysql

        with self.connection_factory.connection_scope(
            profile,
            purpose=ConnectionPurpose.STREAMING_EXPORT,
            read_only=True,
        ) as conn:
            cursor: Any | None = None
            try:
                with _deadline_watchdog(conn, deadline):
                    deadline.check()
                    _configure_mysql_timeout(conn, deadline.timeout_ms)
                    cursor = conn.cursor(pymysql.cursors.SSCursor)
                    cursor.execute(sql)
                    deadline.check()
                    yield from self._yield_rows(cursor, chunk_size, sensitivity, deadline)
            except SQLQueryTimeoutError:
                raise
            except Exception as exc:
                _translate_deadline_error(deadline, exc)
            finally:
                if cursor is not None:
                    cursor.close()
                _reset_mysql_timeout(conn)

    def _yield_rows(
        self,
        cursor: Any,
        chunk_size: int,
        sensitivity: Any,
        deadline: _ExportDeadline,
    ) -> Iterator[dict[str, Any]]:
        columns = [item[0] for item in cursor.description or []]
        yielded = 0
        while yielded < self.max_rows:
            deadline.check()
            rows = cursor.fetchmany(min(chunk_size, self.max_rows - yielded))
            deadline.check()
            if not rows:
                break
            for raw in rows:
                if isinstance(raw, dict):
                    row = {str(column): _serialize_value(value) for column, value in raw.items()}
                else:
                    row = {
                        column: _serialize_value(value)
                        for column, value in zip(columns, raw)
                    }
                yield self._redact(row, sensitivity)
                yielded += 1
                if yielded >= self.max_rows:
                    break
