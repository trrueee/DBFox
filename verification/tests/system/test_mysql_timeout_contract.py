"""MySQL/MariaDB statement timeout contract for read-only execution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import pytest
from pymysql.constants import ER
from pymysql.err import OperationalError

from dlcs.dbfox_data.backend.connection import DataConnectionBoundary, apply_mysql_statement_timeout


class _RecordingCursor:
    def __init__(self, *, reject: tuple[str, ...] = ()) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._reject = reject

    def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
        if any(marker in statement for marker in self._reject):
            raise OperationalError(ER.UNKNOWN_SYSTEM_VARIABLE, "unsupported server variable")
        self.calls.append((statement, parameters))


def test_mysql_uses_max_execution_time_in_milliseconds() -> None:
    cursor = _RecordingCursor()

    apply_mysql_statement_timeout(cursor, 30_000)

    assert cursor.calls == [
        ("SET SESSION max_execution_time = %s", (30_000,)),
    ]


def test_mariadb_falls_back_to_max_statement_time_in_seconds() -> None:
    cursor = _RecordingCursor(reject=("max_execution_time",))

    apply_mysql_statement_timeout(cursor, 30_000)

    assert cursor.calls == [
        ("SET SESSION max_statement_time = %s", (30.0,)),
    ]


def test_unsupported_server_leaves_the_driver_limits_in_effect() -> None:
    cursor = _RecordingCursor(reject=("max_execution_time", "max_statement_time"))

    apply_mysql_statement_timeout(cursor, 30_000)

    assert cursor.calls == []


def test_timeout_setup_propagates_errors_other_than_unknown_variable() -> None:
    class DisconnectedCursor(_RecordingCursor):
        def execute(self, statement, parameters):
            self.calls.append((statement, parameters))
            raise OperationalError(2013, "connection lost")

    cursor = DisconnectedCursor()
    with pytest.raises(OperationalError):
        apply_mysql_statement_timeout(cursor, 1_000)
    assert len(cursor.calls) == 1


def test_mysql_cancellation_leaves_the_connection_with_its_query_owner() -> None:
    class Connection:
        closed = False

        def close(self) -> None:
            self.closed = True

    boundary = DataConnectionBoundary(lambda _id, _kind: None)
    connection = Connection()
    invocation = boundary._reserve("mysql-read")
    boundary._attach(invocation, "mysql", connection)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(boundary.cancel, invocation).result(timeout=2)
        assert boundary._is_cancelled(invocation, None)
        assert not connection.closed
    finally:
        boundary._detach(invocation)
        connection.close()
        boundary._release(invocation)
