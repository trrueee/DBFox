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


def test_mysql_cancel_failure_message_is_sanitized(monkeypatch) -> None:
    registry = QueryRegistry()

    def fail_kill(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("driver leaked user@example.com password='driver-secret'")

    monkeypatch.setattr(registry, "_kill_mysql_query", fail_kill)
    registry.register_mysql(
        execution_id="mysql-sensitive-cancel",
        datasource_id="ds-mysql",
        params={"host": "localhost", "password": "connection-secret"},
        thread_id=321,
    )

    result = registry.cancel("mysql-sensitive-cancel")

    assert result["success"] is False
    assert result["cancelled"] is False
    assert "user@example.com" not in result["message"]
    assert "driver-secret" not in result["message"]
    assert "connection-secret" not in result["message"]
    assert "[REDACTED" in result["message"]


def test_postgres_cancel_failure_message_is_sanitized() -> None:
    registry = QueryRegistry()

    class FakePostgresConnection:
        def cancel(self) -> None:
            raise RuntimeError("cancel failed for admin@example.com password='pg-secret'")

    registry.register_postgres(
        execution_id="postgres-sensitive-cancel",
        datasource_id="ds-postgres",
        connection=FakePostgresConnection(),
    )

    result = registry.cancel("postgres-sensitive-cancel")

    assert result["success"] is False
    assert result["cancelled"] is False
    assert "admin@example.com" not in result["message"]
    assert "pg-secret" not in result["message"]
    assert "[REDACTED" in result["message"]
