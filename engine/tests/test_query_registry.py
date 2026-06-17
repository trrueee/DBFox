from __future__ import annotations

from typing import Any

from engine.query_registry import QueryRegistry


def test_mysql_cancel_uses_parameterized_kill_query(monkeypatch) -> None:
    execute_calls: list[tuple[Any, ...]] = []
    closed = False

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, *args: Any) -> None:
            execute_calls.append(args)

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def close(self) -> None:
            nonlocal closed
            closed = True

    def fake_connect(**_params: Any) -> FakeConnection:
        return FakeConnection()

    monkeypatch.setattr("engine.query_registry.pymysql.connect", fake_connect)

    QueryRegistry()._kill_mysql_query({"host": "localhost"}, 123)

    assert execute_calls == [("KILL QUERY %s", (123,))]
    assert closed is True
