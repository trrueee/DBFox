from __future__ import annotations

import importlib
import logging
from contextlib import contextmanager
from typing import Any

import pytest

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.errors import SQLExecutionError
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault
from engine.sql.row_serializer import FetchSerializationResult, ResultTruncation


def _empty_fetch_result() -> FetchSerializationResult:
    return FetchSerializationResult(
        rows=[],
        columns=[],
        truncation=ResultTruncation(),
        response_bytes=0,
        fetch_ms=0,
        serialize_ms=0,
    )


class _FakeCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.description: list[object] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, params: Any = None) -> None:
        self.calls.append((statement, params))

    def close(self) -> None:
        return None


class _TimeoutSettingFailsCursor(_FakeCursor):
    def __init__(self, exception_secret: str) -> None:
        super().__init__()
        self._exception_secret = exception_secret

    def execute(self, statement: str, params: Any = None) -> None:
        super().execute(statement, params)
        if "MAX_EXECUTION_TIME" in statement or "statement_timeout" in statement:
            raise RuntimeError(self._exception_secret)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.closed = False
        self.rolled_back = False

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_mysql_execution_begins_a_native_read_only_transaction(monkeypatch) -> None:
    import engine.sql.dialect.mysql as mysql

    cursor = _FakeCursor()
    connection = _FakeConnection(cursor)
    vault = InMemoryCredentialVault()
    credential_id = vault.put(kind=CredentialKind.DATASOURCE_PASSWORD, secret="secret")
    profile = ConnectionProfile.from_mapping({
            "id": "source-1-mysql",
            "is_managed": True,
            "connection_generation": 1,
            "db_type": "mysql",
        "host": "db.example.test",
        "database_name": "analytics",
        "username": "readonly",
        "password_credential_id": credential_id,
    })
    factory = ConnectionFactory(vault=vault)
    monkeypatch.setattr(factory, "_pooled_connection", lambda *_args: connection)
    monkeypatch.setattr(mysql, "_fetch_and_serialize", lambda *_args: _empty_fetch_result())

    mysql._execute_on_mysql_profiled(
        "source-1-mysql",
        profile,
        "SELECT 1",
        connection_factory=factory,
    )

    assert cursor.calls[0] == ("START TRANSACTION READ ONLY", None)
    assert ("SELECT 1", None) in cursor.calls
    assert connection.rolled_back is True


def test_postgres_execution_begins_a_native_read_only_transaction(monkeypatch) -> None:
    import engine.sql.dialect.postgres as postgres

    cursor = _FakeCursor()
    connection = _FakeConnection(cursor)
    vault = InMemoryCredentialVault()
    credential_id = vault.put(kind=CredentialKind.DATASOURCE_PASSWORD, secret="secret")
    profile = ConnectionProfile.from_mapping({
            "id": "source-1-postgres",
            "is_managed": True,
            "connection_generation": 1,
            "db_type": "postgresql",
        "host": "db.example.test",
        "database_name": "analytics",
        "username": "readonly",
        "password_credential_id": credential_id,
    })
    factory = ConnectionFactory(vault=vault)
    monkeypatch.setattr(factory, "_pooled_connection", lambda *_args: connection)
    monkeypatch.setattr(postgres, "_fetch_and_serialize", lambda *_args, **_kwargs: _empty_fetch_result())

    postgres._execute_on_postgres_profiled(
        "source-1-postgres",
        profile,
        "SELECT 1",
        connection_factory=factory,
    )

    assert cursor.calls[0] == ("BEGIN READ ONLY", None)
    assert ("SELECT 1", None) in cursor.calls
    assert connection.rolled_back is True


@pytest.mark.parametrize(
    ("dialect", "module_name", "execution_name", "operation"),
    [
        ("mysql", "engine.sql.dialect.mysql", "_execute_on_mysql_profiled", "sql_mysql_timeout_enforcement"),
        ("postgresql", "engine.sql.dialect.postgres", "_execute_on_postgres_profiled", "sql_postgres_timeout_enforcement"),
    ],
)
def test_native_execution_fails_closed_when_server_timeout_cannot_be_enforced(
    monkeypatch,
    caplog,
    dialect: str,
    module_name: str,
    execution_name: str,
    operation: str,
) -> None:
    module = importlib.import_module(module_name)
    sql_secret = "SELECT token FROM users WHERE token = 'timeout-sql-secret'"
    exception_secret = "timeout-driver-secret"
    cursor = _TimeoutSettingFailsCursor(exception_secret)
    connection = _FakeConnection(cursor)
    datasource_id = f"source-timeout-{dialect}"
    vault = InMemoryCredentialVault()
    credential_id = vault.put(kind=CredentialKind.DATASOURCE_PASSWORD, secret="secret")
    profile = ConnectionProfile.from_mapping(
        {
                "id": datasource_id,
                "is_managed": True,
                "connection_generation": 1,
                "db_type": dialect,
            "host": "db.example.test",
            "database_name": "analytics",
            "username": "readonly",
            "password_credential_id": credential_id,
        }
    )
    factory = ConnectionFactory(vault=vault)
    monkeypatch.setattr(factory, "_pooled_connection", lambda *_args: connection)

    with caplog.at_level(logging.WARNING, logger="dbfox.sql.executor"):
        with pytest.raises(SQLExecutionError, match="Unable to enforce"):
            getattr(module, execution_name)(
                datasource_id,
                profile,
                sql_secret,
                connection_factory=factory,
            )

    assert sql_secret not in caplog.text
    assert exception_secret not in caplog.text
    assert f"code={operation}" in caplog.text
    assert "type=RuntimeError" in caplog.text
    assert "fingerprint=" in caplog.text
    assert connection.rolled_back is True
    assert all(statement != sql_secret for statement, _params in cursor.calls)


def test_public_sqlite_executor_forces_read_only_connection(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    import engine.sql.executor as executor
    from engine.schema_sync import sync_schema

    test_datasource.is_read_only = False
    db_session.commit()
    sync_schema(db_session, test_datasource.id)

    observed: dict[str, bool] = {}

    original_scope = ConnectionFactory.connection_scope

    @contextmanager
    def assert_read_only(self: ConnectionFactory, *args: Any, **kwargs: Any):
        observed["read_only"] = bool(kwargs["read_only"])
        with original_scope(self, *args, **kwargs) as connection:
            yield connection

    monkeypatch.setattr(ConnectionFactory, "connection_scope", assert_read_only)
    result = executor.execute_query(
        db_session,
        test_datasource.id,
        "SELECT id FROM users LIMIT 1",
    )

    assert result["success"] is True
    assert observed == {"read_only": True}
