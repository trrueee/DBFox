from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager

import pytest

from engine.errors import SQLQueryTimeoutError


def test_export_deadline_rejects_nonpositive_timeout() -> None:
    from engine.sql.execution.streaming_executor import _ExportDeadline

    with pytest.raises(ValueError, match="timeout"):
        _ExportDeadline(0)


def test_export_deadline_expires_with_a_fixed_safe_error() -> None:
    from engine.sql.execution.streaming_executor import _ExportDeadline

    deadline = _ExportDeadline(1)
    time.sleep(0.05)

    with pytest.raises(SQLQueryTimeoutError, match="Streaming export timed out"):
        deadline.check()


def test_postgres_and_mysql_receive_server_side_statement_limits() -> None:
    from engine.sql.execution.streaming_executor import (
        _configure_mysql_timeout,
        _configure_postgres_timeout,
    )

    class Cursor:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[int, ...] | None]] = []
            self.closed = False

        def execute(self, sql: str, params: tuple[int, ...] | None = None) -> None:
            self.calls.append((sql, params))

        def close(self) -> None:
            self.closed = True

    class Connection:
        def __init__(self) -> None:
            self.cursors: list[Cursor] = []

        def cursor(self, *args, **kwargs) -> Cursor:
            cursor = Cursor()
            self.cursors.append(cursor)
            return cursor

    postgres = Connection()
    mysql = Connection()

    _configure_postgres_timeout(postgres, 12_345)
    _configure_mysql_timeout(mysql, 12_345)

    assert postgres.cursors[0].calls == [("SET LOCAL statement_timeout = %s", (12_345,))]
    assert postgres.cursors[0].closed is True
    assert mysql.cursors[0].calls == [("SET SESSION MAX_EXECUTION_TIME = %s", (12_345,))]
    assert mysql.cursors[0].closed is True


def test_sqlite_progress_handler_and_watchdog_interrupt_an_expired_export() -> None:
    from engine.sql.execution.streaming_executor import (
        _ExportDeadline,
        _deadline_watchdog,
        _install_sqlite_progress_handler,
    )

    class Connection:
        def __init__(self) -> None:
            self.progress: tuple[object | None, int] | None = None
            self.interrupted = False

        def set_progress_handler(self, handler, steps: int) -> None:
            self.progress = (handler, steps)

        def interrupt(self) -> None:
            self.interrupted = True

    connection = Connection()
    deadline = _ExportDeadline(1)
    restore = _install_sqlite_progress_handler(connection, deadline)
    time.sleep(0.05)

    handler, steps = connection.progress or (None, 0)
    assert callable(handler)
    assert steps > 0
    assert handler() == 1
    restore()
    assert connection.progress == (None, 0)

    with _deadline_watchdog(connection, deadline):
        time.sleep(0.05)
    assert connection.interrupted is True


def test_sqlite_streaming_export_interrupts_a_real_long_running_query() -> None:
    from engine.sql.execution.streaming_executor import (
        _ExportDeadline,
        StreamingQueryExecutor,
    )

    connection = sqlite3.connect(":memory:")

    class Factory:
        @contextmanager
        def connection_scope(self, *_args, **_kwargs):
            yield connection

    executor = StreamingQueryExecutor(object(), connection_factory=Factory(), timeout_ms=1)
    sql = (
        "WITH RECURSIVE counter(n) AS ("
        "SELECT 1 UNION ALL SELECT n + 1 FROM counter WHERE n < 10000000"
        ") SELECT sum(n) AS total FROM counter"
    )
    try:
        with pytest.raises(SQLQueryTimeoutError, match="Streaming export timed out"):
            list(executor._stream_sqlite(object(), sql, 100, object(), _ExportDeadline(1)))
    finally:
        connection.close()
