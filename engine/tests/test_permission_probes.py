from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.sql.permissions import (
    MySQLPermissionProbe,
    PostgresPermissionProbe,
    SQLitePermissionProbe,
)


class _CursorContext:
    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def __enter__(self) -> Any:
        return self.cursor

    def __exit__(self, *_exc: object) -> None:
        return None


class _Connection:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def cursor(self) -> _CursorContext:
        return _CursorContext(self._cursor)


class _PostgresCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql: str, *_args: object) -> None:
        self.executed.append(sql)

    def fetchall(self) -> list[tuple[str, str, bool, bool, bool]]:
        return [
            ("public", "orders", True, False, True),
            ("public", "customers", False, False, False),
        ]


def test_postgres_probe_uses_table_privileges_not_transaction_flag() -> None:
    cursor = _PostgresCursor()

    report = PostgresPermissionProbe().probe(_Connection(cursor))

    sql = "\n".join(cursor.executed)
    assert "has_table_privilege" in sql
    assert "'INSERT'" in sql
    assert "'UPDATE'" in sql
    assert "'DELETE'" in sql
    assert "transaction_read_only" not in sql
    assert report.readonly is False
    assert report.writable_privileges == [
        "public.orders:INSERT",
        "public.orders:DELETE",
    ]
    assert report.evidence["checked_tables"] == 2


class _SQLiteCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def fetchone(self) -> tuple[int]:
        return (1,)


def test_sqlite_probe_reports_connection_and_file_write_state(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    db_path = tmp_path / "db.sqlite"
    db_path.write_text("", encoding="utf-8")
    cursor = _SQLiteCursor()
    monkeypatch.setattr("engine.sql.permissions.sqlite.os.access", lambda *_args: True)

    report = SQLitePermissionProbe(database_path=db_path).probe(_Connection(cursor))

    assert cursor.executed == ["PRAGMA query_only"]
    assert report.readonly is True
    assert report.writable_privileges == []
    assert report.evidence["connection_readonly"] is True
    assert report.evidence["file_writable"] is True


class _MySQLCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql: str, *_args: object) -> None:
        self.executed.append(sql)

    def fetchall(self) -> list[tuple[str]]:
        return [
            ("GRANT SELECT, INSERT, UPDATE ON `db`.* TO 'user'@'%'",),
            ("GRANT SELECT ON `analytics`.* TO 'user'@'%'",),
        ]


def test_mysql_probe_reports_writable_grants() -> None:
    cursor = _MySQLCursor()

    report = MySQLPermissionProbe().probe(_Connection(cursor))

    assert cursor.executed == ["SHOW GRANTS FOR CURRENT_USER()"]
    assert report.readonly is False
    assert report.writable_privileges == ["INSERT", "UPDATE"]
    assert len(report.evidence["grants"]) == 2
