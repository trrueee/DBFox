from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.connectivity.profile import ConnectionProfile
from engine.query_registry import QueryRegistry


def _mysql_profile() -> ConnectionProfile:
    return ConnectionProfile.from_mapping(
        {
            "id": "ds-mysql",
            "is_managed": True,
            "connection_generation": 1,
            "db_type": "mysql",
            "host": "localhost",
            "port": 3306,
            "database_name": "warehouse",
            "username": "readonly",
            "password_credential_id": "cred_datasource_password_test",
        }
    )


def test_mysql_cancel_uses_parameterized_kill_query() -> None:
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

    class FakeConnectionFactory:
        @contextmanager
        def connection_scope(self, *_args: Any, **_kwargs: Any):
            connection = FakeConnection()
            try:
                yield connection
            finally:
                connection.close()

    registry = QueryRegistry(connection_factory=FakeConnectionFactory())

    registry._kill_mysql_query(_mysql_profile(), 123)

    assert execute_calls == [("KILL QUERY %s", (123,))]
    assert closed is True


def test_mysql_cancel_failure_uses_fixed_error_catalog(monkeypatch) -> None:
    registry = QueryRegistry()

    def fail_kill(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("driver leaked user@example.com password='driver-secret'")

    monkeypatch.setattr(registry, "_kill_mysql_query", fail_kill)
    registry.register_mysql(
        execution_id="mysql-sensitive-cancel",
        datasource_id="ds-mysql",
        profile=_mysql_profile(),
        thread_id=321,
    )

    result = registry.cancel("mysql-sensitive-cancel")

    assert result["success"] is False
    assert result["cancelled"] is False
    assert "user@example.com" not in result["message"]
    assert "driver-secret" not in result["message"]
    assert result["message"] == fixed_error_message(FixedErrorCode.QUERY_CANCELLATION_FAILED)


def test_postgres_cancel_failure_uses_fixed_error_catalog() -> None:
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
    assert result["message"] == fixed_error_message(FixedErrorCode.QUERY_CANCELLATION_FAILED)
