import logging
import uuid
from typing import Any

import pymysql
import pytest

from engine.environment.schema_introspector import SchemaIntrospector
from engine.errors import DataSourceConnectionError
from engine.models import DataSource
from engine.security.credential_vault import CredentialVaultUnavailableError


def test_decrypt_datasource_password_fails_closed_without_a_credential(db_session):
    ds = DataSource(
        id=str(uuid.uuid4()),
        name="mysql probe",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name="creatorhub",
        username="root",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    with pytest.raises(DataSourceConnectionError, match="password credential"):
        SchemaIntrospector()._decrypt_datasource_password(db_session, ds.id)


class _FakeCursor:
    def __init__(self, dialect: str) -> None:
        self.dialect = dialect
        self.rows: list[tuple[Any, ...]] = []
        self.description: list[tuple[str]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        query = " ".join(sql.lower().split())
        self.description = []

        if "information_schema.tables" in query:
            if self.dialect == "postgres":
                self.rows = [("public", "orders", "BASE TABLE", "orders table", 42)]
            else:
                self.rows = [("main", "orders", "BASE TABLE", "orders table")]
            return

        if "information_schema.columns" in query:
            if self.dialect == "postgres":
                self.rows = [
                    ("id", "integer", "integer", "NO", None, True, False, "id comment"),
                    ("customer_id", "integer", "integer", "YES", None, False, True, "cust comment"),
                ]
            else:
                self.rows = [
                    ("id", "integer", "integer", "NO", None, True, False),
                    ("customer_id", "integer", "integer", "YES", None, False, True),
                ]
            return

        if "table_constraints" in query and "primary key" in query:
            self.rows = [("id",)]
            return

        if "key_column_usage" in query:
            self.rows = [("customer_id", "customers", "id")]
            return

        if "select count(*)" in query:
            self.rows = [(2,)]
            return

        if "select * from" in query:
            self.description = [("id",), ("customer_id",)]
            self.rows = [(1, 10), (2, 11)]
            return

        self.rows = []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None


class _FakeConnection:
    def __init__(self, dialect: str) -> None:
        self.dialect = dialect
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.dialect)

    def close(self) -> None:
        self.closed = True


def _add_datasource(db_session, db_type: str) -> DataSource:
    ds = DataSource(
        id=str(uuid.uuid4()),
        name=f"{db_type} probe",
        db_type=db_type,
        host="127.0.0.1",
        port=5432 if db_type == "postgres" else 0,
        database_name="analytics",
        username="dbfox",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()
    return ds


def test_vault_unavailable_never_calls_mysql_driver(db_session, monkeypatch) -> None:
    datasource = _add_datasource(db_session, "mysql")
    datasource.password_credential_id = "cred_datasource_password_unavailable"
    db_session.commit()
    driver_calls: list[dict[str, Any]] = []

    class UnavailableVault:
        def get(self, *_args: Any, **_kwargs: Any) -> str:
            raise CredentialVaultUnavailableError()

    monkeypatch.setattr(
        "engine.environment.schema_introspector.get_credential_vault",
        lambda: UnavailableVault(),
    )
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: driver_calls.append(kwargs))

    with pytest.raises(CredentialVaultUnavailableError) as exc_info:
        SchemaIntrospector().inspect(db_session, datasource.id)

    assert exc_info.value.code == "CREDENTIAL_VAULT_UNAVAILABLE"
    assert driver_calls == []


def test_vault_unavailable_never_calls_postgres_driver(db_session, monkeypatch) -> None:
    psycopg2 = pytest.importorskip("psycopg2")
    datasource = _add_datasource(db_session, "postgres")
    datasource.password_credential_id = "cred_datasource_password_unavailable"
    db_session.commit()
    driver_calls: list[dict[str, Any]] = []

    class UnavailableVault:
        def get(self, *_args: Any, **_kwargs: Any) -> str:
            raise CredentialVaultUnavailableError()

    monkeypatch.setattr(
        "engine.environment.schema_introspector.get_credential_vault",
        lambda: UnavailableVault(),
    )
    monkeypatch.setattr(psycopg2, "connect", lambda **kwargs: driver_calls.append(kwargs))

    with pytest.raises(CredentialVaultUnavailableError) as exc_info:
        SchemaIntrospector().inspect(db_session, datasource.id)

    assert exc_info.value.code == "CREDENTIAL_VAULT_UNAVAILABLE"
    assert driver_calls == []


def test_ssh_tunnel_failure_never_falls_back_to_direct_mysql(db_session, monkeypatch) -> None:
    datasource = _add_datasource(db_session, "mysql")
    datasource.ssh_enabled = True
    datasource.ssh_host = "jump.example.test"
    datasource.ssh_username = "dbfox"
    db_session.commit()
    driver_calls: list[dict[str, Any]] = []

    def fail_tunnel(_config: dict[str, Any]) -> Any:
        raise RuntimeError("tunnel-sentinel")

    monkeypatch.setattr("engine.datasource.get_or_create_tunnel_for_dict", fail_tunnel)
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: driver_calls.append(kwargs))

    with pytest.raises(DataSourceConnectionError) as exc_info:
        SchemaIntrospector().inspect(db_session, datasource.id)

    assert exc_info.value.code == "CONNECTION_FAILED"
    assert driver_calls == []


def test_mysql_connection_error_never_logs_vault_or_driver_secret(
    db_session,
    monkeypatch,
    caplog,
) -> None:
    datasource = _add_datasource(db_session, "mysql")
    introspector = SchemaIntrospector()
    sentinel = "mysql-introspection-secret-sentinel"

    monkeypatch.setattr(
        introspector,
        "_decrypt_datasource_password",
        lambda _db, _datasource_id: sentinel,
    )

    def fail_connect(**_kwargs: Any) -> None:
        raise RuntimeError(f"MySQL rejected password={sentinel}")

    monkeypatch.setattr(pymysql, "connect", fail_connect)

    with caplog.at_level(logging.WARNING, logger="dbfox.environment.schema_introspector"):
        inventory = introspector.inspect(db_session, datasource.id)

    assert inventory.table_count == 0
    assert inventory.tables == []
    assert sentinel not in str(inventory)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_duckdb_connection_error_never_logs_driver_secret(
    db_session,
    monkeypatch,
    caplog,
) -> None:
    datasource = _add_datasource(db_session, "duckdb")
    introspector = SchemaIntrospector()
    sentinel = "duckdb-introspection-secret-sentinel"

    def fail_connect(_resolved: Any) -> None:
        raise RuntimeError(f"DuckDB driver failed with token={sentinel}")

    monkeypatch.setattr(introspector, "_connect_duckdb", fail_connect)

    with caplog.at_level(logging.WARNING, logger="dbfox.environment.schema_introspector"):
        inventory = introspector.inspect(db_session, datasource.id)

    assert inventory.table_count == 0
    assert inventory.tables == []
    assert sentinel not in str(inventory)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_postgres_introspection_returns_tables_columns_fks_and_samples(db_session, monkeypatch):
    ds = _add_datasource(db_session, "postgres")
    fake_conn = _FakeConnection("postgres")
    introspector = SchemaIntrospector()
    monkeypatch.setattr(
        introspector,
        "_connect_postgres",
        lambda db, resolved, tunnel=None: fake_conn,
        raising=False,
    )

    inventory = introspector.inspect(db_session, ds.id)

    assert fake_conn.closed is True
    assert inventory.dialect == "postgres"
    assert inventory.database_name == "analytics"
    assert inventory.table_count == 1
    assert inventory.column_count == 2
    table = inventory.tables[0]
    assert table.table_schema == "public"
    assert table.table_name == "orders"
    assert table.table_type == "table"
    assert table.comment == "orders table"
    assert table.row_count_estimate == 42
    assert table.columns[0].column_name == "id"
    assert table.columns[0].is_primary_key is True
    assert table.columns[1].is_foreign_key is True
    assert table.foreign_keys[0].column_name == "customer_id"
    assert table.foreign_keys[0].referenced_table == "customers"
    assert table.sample_rows == [{"id": 1, "customer_id": 10}, {"id": 2, "customer_id": 11}]


def test_duckdb_introspection_returns_tables_columns_fks_and_samples(db_session, monkeypatch):
    ds = _add_datasource(db_session, "duckdb")
    fake_conn = _FakeConnection("duckdb")
    introspector = SchemaIntrospector()
    monkeypatch.setattr(
        introspector,
        "_connect_duckdb",
        lambda resolved: fake_conn,
        raising=False,
    )

    inventory = introspector.inspect(db_session, ds.id)

    assert fake_conn.closed is True
    assert inventory.dialect == "duckdb"
    assert inventory.database_name == "analytics"
    assert inventory.table_count == 1
    assert inventory.column_count == 2
    table = inventory.tables[0]
    assert table.table_schema == "main"
    assert table.table_name == "orders"
    assert table.row_count_estimate == 2
    assert table.columns[0].is_primary_key is True
    assert table.columns[1].is_foreign_key is True
    assert table.foreign_keys[0].referenced_column == "id"
    assert table.sample_rows == [{"id": 1, "customer_id": 10}, {"id": 2, "customer_id": 11}]
