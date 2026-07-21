from __future__ import annotations

import sqlite3
from typing import Any

import pytest

import engine.tools.db.inspect as inspect_module
from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.resources import ConnectionResources
from engine.errors import DataSourceConnectionError
from engine.models import DataSource
from engine.security.credential_vault import (
    CredentialKind,
    CredentialVaultUnavailableError,
    InMemoryCredentialVault,
)


class _MySQLConnection:
    def __init__(self) -> None:
        self.pinged = False
        self.closed = False

    def ping(self, reconnect: bool = True) -> None:
        self.pinged = reconnect

    def cursor(self) -> Any:
        return _ReadOnlyCursor()

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _PostgresConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def cursor(self) -> Any:
        return _ReadOnlyCursor()

    def rollback(self) -> None:
        return None


class _ReadOnlyCursor:
    def execute(self, _sql: str, _params: Any = None) -> None:
        return None

    def close(self) -> None:
        return None


def _network_datasource(
    *,
    datasource_id: str,
    dialect: str,
    password_credential_id: str,
) -> DataSource:
    return DataSource(
        id=datasource_id,
        name=f"{dialect}-inspect",
        db_type=dialect,
        host="db.internal.test",
        port=5432 if dialect == "postgresql" else 3306,
        database_name="warehouse",
        username="readonly",
        password_credential_id=password_credential_id,
        connection_generation=1,
        status="active",
    )


def test_sqlite_inspector_uses_factory_and_opens_read_only(tmp_path, db_session) -> None:
    database_path = tmp_path / "inspection.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY)")

    datasource = DataSource(
        id="sqlite-inspect",
        name="sqlite-inspect",
        db_type="sqlite",
        host=None,
        port=0,
        database_name=str(database_path),
        username=None,
        connection_generation=1,
        status="active",
    )

    class TrackingFactory(ConnectionFactory):
        def __init__(self) -> None:
            super().__init__(vault=InMemoryCredentialVault())
            self.seen_database_name: str | None = None

        def sqlite_path(self, profile):
            self.seen_database_name = profile.database_name
            return super().sqlite_path(profile)

    factory = TrackingFactory()
    inspector = inspect_module.SQLiteInspector(
        db_session,
        datasource,
        "orders",
        connection_factory=factory,
    )

    with inspector.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE forbidden_write (id INTEGER)")

    assert factory.seen_database_name == str(database_path)


def test_mysql_inspector_resolves_vault_secret_through_factory(db_session, monkeypatch) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="mysql-vault-secret",
    )
    datasource = _network_datasource(
        datasource_id="mysql-inspect",
        dialect="mysql",
        password_credential_id=credential_id,
    )
    connection = _MySQLConnection()
    captured_endpoint: dict[str, Any] = {}
    factory = ConnectionFactory(vault=vault)
    monkeypatch.setattr(
        factory,
        "_pooled_connection",
        lambda profile, endpoint: (
            captured_endpoint.update(
                {
                    "credential_id": profile.password_credential_id,
                    "host": endpoint.host,
                    "port": endpoint.port,
                }
            )
            or connection
        ),
    )
    inspector = inspect_module.MySQLInspector(
        db_session,
        datasource,
        "orders",
        connection_factory=factory,
    )
    with inspector.connect() as active_connection:
        assert active_connection is connection

    assert connection.closed is True
    assert captured_endpoint["credential_id"] == credential_id
    assert captured_endpoint["host"] == "db.internal.test"


def test_postgres_inspector_resolves_vault_secret_through_factory(db_session, monkeypatch) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="postgres-vault-secret",
    )
    datasource = _network_datasource(
        datasource_id="postgres-inspect",
        dialect="postgresql",
        password_credential_id=credential_id,
    )
    connection = _PostgresConnection()
    captured_endpoint: dict[str, Any] = {}
    factory = ConnectionFactory(vault=vault)
    monkeypatch.setattr(
        factory,
        "_pooled_connection",
        lambda profile, endpoint: (
            captured_endpoint.update(
                {
                    "credential_id": profile.password_credential_id,
                    "host": endpoint.host,
                    "port": endpoint.port,
                }
            )
            or connection
        ),
    )
    inspector = inspect_module.PostgreSQLInspector(
        db_session,
        datasource,
        "public.orders",
        connection_factory=factory,
    )
    with inspector.connect() as active_connection:
        assert active_connection is connection

    assert connection.closed is True
    assert captured_endpoint["credential_id"] == credential_id
    assert captured_endpoint["port"] == 5432


def test_mysql_inspector_ssh_failure_never_falls_back_to_direct_pool(
    db_session,
    monkeypatch,
) -> None:
    vault = InMemoryCredentialVault()
    password_credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="database-secret",
    )
    ssh_password_credential_id = vault.put(
        kind=CredentialKind.SSH_PASSWORD,
        secret="jumpbox-secret",
    )
    datasource = _network_datasource(
        datasource_id="mysql-ssh-inspect",
        dialect="mysql",
        password_credential_id=password_credential_id,
    )
    datasource.ssh_enabled = True
    datasource.ssh_host = "jump.internal.test"
    datasource.ssh_username = "jump-user"
    datasource.ssh_password_credential_id = ssh_password_credential_id
    pool_calls: list[dict[str, Any]] = []

    def fail_tunnel(_config: dict[str, Any]) -> Any:
        raise RuntimeError("jumpbox-secret must not reach the caller")

    factory = ConnectionFactory(
        vault=vault,
        resources=ConnectionResources(managed_tunnel_opener=fail_tunnel),
    )
    monkeypatch.setattr(
        factory,
        "_pooled_connection",
        lambda _profile, params: pool_calls.append(dict(params)),
    )
    inspector = inspect_module.MySQLInspector(
        db_session,
        datasource,
        "orders",
        connection_factory=factory,
    )

    with pytest.raises(DataSourceConnectionError) as exc_info:
        with inspector.connect():
            pytest.fail("SSH tunnel failure must not use the datasource host directly.")

    assert "jumpbox-secret" not in str(exc_info.value)
    assert pool_calls == []


def test_mysql_inspector_vault_failure_never_calls_driver(db_session, monkeypatch) -> None:
    datasource = _network_datasource(
        datasource_id="mysql-vault-failure-inspect",
        dialect="mysql",
        password_credential_id="cred_datasource_password_missing",
    )
    driver_calls: list[dict[str, Any]] = []

    class UnavailableVault:
        def get(self, *_args: Any, **_kwargs: Any) -> str:
            raise CredentialVaultUnavailableError()

    factory = ConnectionFactory(vault=UnavailableVault())
    monkeypatch.setattr(
        "engine.connectivity._pools.pymysql.connect",
        lambda **params: driver_calls.append(params),
    )
    inspector = inspect_module.MySQLInspector(
        db_session,
        datasource,
        "orders",
        connection_factory=factory,
    )

    with pytest.raises(CredentialVaultUnavailableError):
        with inspector.connect():
            pytest.fail("A vault failure must stop before pool creation.")

    assert driver_calls == []
