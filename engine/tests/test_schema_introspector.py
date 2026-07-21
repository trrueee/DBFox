import logging
import ssl
import uuid
from contextlib import contextmanager
from typing import Any

import pymysql
import pytest

import engine.environment.schema_introspector as schema_introspector_module
from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionPurpose
from engine.environment.authoritative_inventory import (
    SchemaInspectionError,
    SchemaInspectionErrorCode,
)
from engine.environment.schema_introspector import SchemaIntrospector
from engine.errors import DataSourceConnectionError
from engine.models import DataSource
from engine.security.credential_vault import CredentialVaultUnavailableError


@contextmanager
def _capture_module_logger(monkeypatch, caplog, module, level: int):
    """Inject an unregistered logger so this test does not alter app logging."""
    capture_logger = logging.Logger(f"test.{module.__name__}.boundary")
    capture_logger.setLevel(level)
    capture_logger.propagate = False
    capture_logger.addHandler(caplog.handler)
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(module, "logger", capture_logger)
            yield
    finally:
        capture_logger.removeHandler(caplog.handler)


def test_network_inspection_fails_closed_without_a_credential_reference(db_session):
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

    with pytest.raises(SchemaInspectionError) as exc_info:
        SchemaIntrospector().inspect(db_session, ds.id)

    assert exc_info.value.code == SchemaInspectionErrorCode.CREDENTIAL_UNAVAILABLE


class _FakeCursor:
    def __init__(self, dialect: str) -> None:
        self.dialect = dialect
        self.rows: list[Any] = []
        self.description: list[tuple[str]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        query = " ".join(sql.lower().split())
        self.description = []

        if "information_schema.tables" in query:
            if self.dialect == "postgres":
                self.rows = [("public", "orders", "BASE TABLE", "orders table", 42)]
            elif self.dialect == "mysql":
                self.rows = [{
                    "TABLE_NAME": "orders",
                    "TABLE_TYPE": "BASE TABLE",
                    "TABLE_COMMENT": "orders table",
                    "TABLE_ROWS": 42,
                }]
            else:
                self.rows = [("main", "orders", "BASE TABLE", "orders table")]
            return

        if "information_schema.columns" in query:
            if self.dialect == "postgres":
                self.rows = [
                    ("id", "integer", "integer", "NO", None, True, False, "id comment"),
                    ("customer_id", "integer", "integer", "YES", None, False, True, "cust comment"),
                ]
            elif self.dialect == "mysql":
                self.rows = [
                    {
                        "COLUMN_NAME": "id",
                        "DATA_TYPE": "integer",
                        "COLUMN_TYPE": "integer",
                        "IS_NULLABLE": "NO",
                        "COLUMN_DEFAULT": None,
                        "COLUMN_KEY": "PRI",
                        "COLUMN_COMMENT": "id comment",
                    },
                    {
                        "COLUMN_NAME": "customer_id",
                        "DATA_TYPE": "integer",
                        "COLUMN_TYPE": "integer",
                        "IS_NULLABLE": "YES",
                        "COLUMN_DEFAULT": None,
                        "COLUMN_KEY": "MUL",
                        "COLUMN_COMMENT": "cust comment",
                    },
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
            self.rows = (
                [{
                    "COLUMN_NAME": "customer_id",
                    "REFERENCED_TABLE_NAME": "customers",
                    "REFERENCED_COLUMN_NAME": "id",
                }]
                if self.dialect == "mysql"
                else [("customer_id", "customers", "id")]
            )
            return

        if "select count(*)" in query:
            self.rows = [(2,)]
            return

        if "select * from" in query:
            self.description = [("id",), ("customer_id",)]
            self.rows = [(1, 10), (2, 11)]
            return

        self.rows = []

    def fetchall(self) -> list[Any]:
        return self.rows

    def fetchone(self) -> Any | None:
        return self.rows[0] if self.rows else None


class _FakeConnection:
    def __init__(self, dialect: str) -> None:
        self.dialect = dialect
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.dialect)

    def close(self) -> None:
        self.closed = True


class _StaticConnectionFactory:
    """A connection-boundary double; inspectors must not bypass it."""

    def __init__(
        self,
        connection: Any | None = None,
        error: Exception | None = None,
        duckdb_connection: Any | None = None,
    ) -> None:
        self.connection = connection
        self.error = error
        self.duckdb_connection = duckdb_connection
        self.profiles: list[Any] = []
        self.purposes: list[ConnectionPurpose] = []

    @contextmanager
    def connection_scope(
        self,
        profile: Any,
        *,
        purpose: ConnectionPurpose,
        read_only: bool,
        pooled: bool = True,
        sqlite_row_factory: Any | None = None,
    ):
        del read_only, pooled, sqlite_row_factory
        self.profiles.append(profile)
        self.purposes.append(purpose)
        if self.error is not None:
            raise self.error
        connection = self.duckdb_connection or self.connection
        if connection is None:
            raise AssertionError("Connection scope requires a fake connection")
        try:
            yield connection
        finally:
            connection.close()


def _add_datasource(db_session, db_type: str) -> DataSource:
    ds = DataSource(
        id=str(uuid.uuid4()),
        name=f"{db_type} probe",
        db_type=db_type,
        host="127.0.0.1",
        port=5432 if db_type == "postgres" else (3306 if db_type == "mysql" else 0),
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

    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: driver_calls.append(kwargs))

    with pytest.raises(SchemaInspectionError) as exc_info:
        SchemaIntrospector(
            connection_factory=ConnectionFactory(vault=UnavailableVault())
        ).inspect(db_session, datasource.id)

    assert exc_info.value.code == SchemaInspectionErrorCode.CREDENTIAL_UNAVAILABLE
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

    monkeypatch.setattr(psycopg2, "connect", lambda **kwargs: driver_calls.append(kwargs))

    with pytest.raises(SchemaInspectionError) as exc_info:
        SchemaIntrospector(
            connection_factory=ConnectionFactory(vault=UnavailableVault())
        ).inspect(db_session, datasource.id)

    assert exc_info.value.code == SchemaInspectionErrorCode.CREDENTIAL_UNAVAILABLE
    assert driver_calls == []


def test_ssh_tunnel_failure_never_falls_back_to_direct_mysql(db_session, monkeypatch) -> None:
    datasource = _add_datasource(db_session, "mysql")
    datasource.password_credential_id = "cred_datasource_password"
    datasource.ssh_enabled = True
    datasource.ssh_host = "jump.example.test"
    datasource.ssh_username = "dbfox"
    datasource.ssh_password_credential_id = "cred_ssh_password"
    db_session.commit()
    driver_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: driver_calls.append(kwargs))

    with pytest.raises(SchemaInspectionError) as exc_info:
        SchemaIntrospector(
            connection_factory=_StaticConnectionFactory(
                error=DataSourceConnectionError("SSH tunnel unavailable")
            )
        ).inspect(db_session, datasource.id)

    assert exc_info.value.code == SchemaInspectionErrorCode.SSH_FAILED
    assert driver_calls == []


def test_mysql_connection_error_never_logs_vault_or_driver_secret(
    db_session,
    monkeypatch,
    caplog,
) -> None:
    datasource = _add_datasource(db_session, "mysql")
    datasource.password_credential_id = "cred_datasource_password"
    db_session.commit()
    sentinel = "mysql-introspection-secret-sentinel"
    factory = _StaticConnectionFactory(
        error=RuntimeError(f"MySQL rejected password={sentinel}")
    )
    introspector = SchemaIntrospector(connection_factory=factory)

    with _capture_module_logger(
        monkeypatch, caplog, schema_introspector_module, logging.WARNING
    ):
        with pytest.raises(SchemaInspectionError) as exc_info:
            introspector.inspect(db_session, datasource.id)

    assert exc_info.value.code == SchemaInspectionErrorCode.CONNECTION_FAILED
    assert sentinel not in str(exc_info.value)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert factory.purposes == [ConnectionPurpose.SCHEMA_SYNC]


def test_mysql_tls_failure_is_a_typed_inspection_error(db_session, monkeypatch) -> None:
    datasource = _add_datasource(db_session, "mysql")
    datasource.password_credential_id = "cred_datasource_password"
    db_session.commit()
    introspector = SchemaIntrospector(
        connection_factory=_StaticConnectionFactory(
            error=ssl.SSLError("simulated TLS handshake failure")
        )
    )

    with pytest.raises(SchemaInspectionError) as exc_info:
        introspector.inspect(db_session, datasource.id)

    assert exc_info.value.code == SchemaInspectionErrorCode.TLS_FAILED


def test_mysql_introspection_uses_factory_params_and_dict_cursor_rows(db_session, monkeypatch) -> None:
    datasource = _add_datasource(db_session, "mysql")
    datasource.password_credential_id = "cred_datasource_password"
    db_session.commit()
    fake_conn = _FakeConnection("mysql")
    factory = _StaticConnectionFactory(connection=fake_conn)
    introspector = SchemaIntrospector(connection_factory=factory)

    inventory = introspector.inspect(db_session, datasource.id)

    assert fake_conn.closed is True
    assert inventory.table_count == 1
    assert inventory.tables[0].table_name == "orders"
    assert inventory.tables[0].columns[0].is_primary_key is True
    assert inventory.tables[0].foreign_keys[0].referenced_table == "customers"
    assert factory.purposes == [ConnectionPurpose.SCHEMA_SYNC]


def test_duckdb_connection_error_never_logs_driver_secret(
    db_session,
    monkeypatch,
    caplog,
) -> None:
    datasource = _add_datasource(db_session, "duckdb")
    sentinel = "duckdb-introspection-secret-sentinel"

    introspector = SchemaIntrospector(
        connection_factory=_StaticConnectionFactory(
            error=RuntimeError(f"DuckDB driver failed with token={sentinel}")
        )
    )

    with _capture_module_logger(
        monkeypatch, caplog, schema_introspector_module, logging.WARNING
    ):
        with pytest.raises(SchemaInspectionError) as exc_info:
            introspector.inspect(db_session, datasource.id)

    assert exc_info.value.code == SchemaInspectionErrorCode.CONNECTION_FAILED
    assert sentinel not in str(exc_info.value)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_postgres_introspection_returns_tables_columns_fks_and_samples(db_session, monkeypatch):
    ds = _add_datasource(db_session, "postgres")
    ds.password_credential_id = "cred_datasource_password"
    db_session.commit()
    fake_conn = _FakeConnection("postgres")
    factory = _StaticConnectionFactory(connection=fake_conn)
    introspector = SchemaIntrospector(connection_factory=factory)

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
    assert factory.purposes == [ConnectionPurpose.SCHEMA_SYNC]


def test_duckdb_introspection_returns_tables_columns_fks_and_samples(db_session, monkeypatch):
    ds = _add_datasource(db_session, "duckdb")
    fake_conn = _FakeConnection("duckdb")
    factory = _StaticConnectionFactory(duckdb_connection=fake_conn)
    introspector = SchemaIntrospector(connection_factory=factory)

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
    assert factory.purposes == [ConnectionPurpose.SCHEMA_SYNC]


def test_duckdb_memory_datasource_is_not_an_authoritative_catalog_source(db_session) -> None:
    datasource = _add_datasource(db_session, "duckdb")
    datasource.database_name = ":memory:"
    db_session.commit()

    with pytest.raises(SchemaInspectionError) as exc_info:
        SchemaIntrospector().inspect(db_session, datasource.id)

    assert exc_info.value.code == SchemaInspectionErrorCode.DUCKDB_MEMORY_UNSUPPORTED
