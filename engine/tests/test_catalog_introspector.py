from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from typing import Any, Generator

import pytest

from engine.connectivity.factory import ConnectionFactory
from engine.environment.authoritative_inventory import (
    SchemaInspectionError,
    SchemaInspectionErrorCode,
)
from engine.environment.catalog_introspector import CatalogIntrospector
from engine.errors import DataSourceConnectionError
from engine.models import DataSource
from engine.security.credential_vault import CredentialVaultUnavailableError


def test_sqlite_catalog_reflection_returns_tables_columns_and_foreign_keys(
    db_session,
    test_datasource,
) -> None:
    inventory = CatalogIntrospector().inspect_catalog(
        db_session,
        test_datasource.id,
    )

    assert inventory.datasource_id == test_datasource.id
    assert inventory.dialect == "sqlite"
    assert inventory.table_count >= 20
    orders = next(table for table in inventory.tables if table.table_name == "orders")
    assert orders.table_schema == "main"
    assert any(column.column_name == "user_id" for column in orders.columns)
    assert any(
        foreign_key.column_name == "user_id"
        and foreign_key.referenced_table == "users"
        and foreign_key.referenced_column == "id"
        for foreign_key in orders.foreign_keys
    )


def test_explicit_object_targets_share_one_managed_connection(
    db_session,
    test_datasource,
) -> None:
    class TrackingFactory(ConnectionFactory):
        calls = 0

        @contextmanager
        def sqlalchemy_connection_scope(
            self,
            *args: Any,
            **kwargs: Any,
        ) -> Generator[Any, None, None]:
            self.calls += 1
            with super().sqlalchemy_connection_scope(*args, **kwargs) as connection:
                yield connection

    factory = TrackingFactory()
    results = CatalogIntrospector(
        connection_factory=factory,
    ).inspect_objects(
        db_session,
        test_datasource.id,
        ["orders", "orders.user_id"],
    )

    assert factory.calls == 1
    assert [result.object_type for result in results] == ["table", "column"]


def test_live_object_inspection_has_no_process_cache(
    db_session,
    test_datasource,
) -> None:
    introspector = CatalogIntrospector()
    first = introspector.inspect_objects(
        db_session,
        test_datasource.id,
        ["orders"],
    )[0]
    assert not any(column.name == "fresh_column" for column in first.columns)

    connection = sqlite3.connect(test_datasource.database_name)
    try:
        connection.execute("ALTER TABLE orders ADD COLUMN fresh_column TEXT")
        connection.commit()
    finally:
        connection.close()

    second = introspector.inspect_objects(
        db_session,
        test_datasource.id,
        ["orders"],
    )[0]
    assert any(column.name == "fresh_column" for column in second.columns)


def test_network_inspection_fails_closed_without_credential_reference(
    db_session,
    test_datasource,
) -> None:
    test_datasource.db_type = "mysql"
    test_datasource.host = "127.0.0.1"
    test_datasource.port = 3306
    test_datasource.database_name = "app"
    test_datasource.username = "readonly"
    test_datasource.password_credential_id = None
    db_session.commit()

    with pytest.raises(SchemaInspectionError) as exc_info:
        CatalogIntrospector().inspect_catalog(db_session, test_datasource.id)

    assert exc_info.value.code == SchemaInspectionErrorCode.CREDENTIAL_UNAVAILABLE


@pytest.mark.parametrize(
    ("db_type", "expected_code"),
    [
        ("mysql", SchemaInspectionErrorCode.CREDENTIAL_UNAVAILABLE),
        ("postgresql", SchemaInspectionErrorCode.CREDENTIAL_UNAVAILABLE),
    ],
)
def test_vault_failure_is_typed_and_never_reaches_a_driver(
    db_session,
    test_datasource,
    db_type: str,
    expected_code: SchemaInspectionErrorCode,
) -> None:
    class VaultFailureFactory(ConnectionFactory):
        @contextmanager
        def sqlalchemy_connection_scope(
            self,
            *args: Any,
            **kwargs: Any,
        ) -> Generator[Any, None, None]:
            raise CredentialVaultUnavailableError()
            yield

    test_datasource.db_type = db_type
    test_datasource.host = "127.0.0.1"
    test_datasource.port = 5432 if db_type == "postgresql" else 3306
    test_datasource.database_name = "app"
    test_datasource.username = "readonly"
    test_datasource.password_credential_id = "cred_missing"
    db_session.commit()

    with pytest.raises(SchemaInspectionError) as exc_info:
        CatalogIntrospector(
            connection_factory=VaultFailureFactory(),
        ).inspect_catalog(db_session, test_datasource.id)

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    ("ssh_enabled", "ssl_enabled", "expected_code"),
    [
        (True, False, SchemaInspectionErrorCode.SSH_FAILED),
        (False, True, SchemaInspectionErrorCode.TLS_FAILED),
        (False, False, SchemaInspectionErrorCode.CONNECTION_FAILED),
    ],
)
def test_connection_failure_classification_uses_profile_metadata(
    db_session,
    test_datasource,
    ssh_enabled: bool,
    ssl_enabled: bool,
    expected_code: SchemaInspectionErrorCode,
) -> None:
    class ConnectionFailureFactory(ConnectionFactory):
        @contextmanager
        def sqlalchemy_connection_scope(
            self,
            *args: Any,
            **kwargs: Any,
        ) -> Generator[Any, None, None]:
            raise DataSourceConnectionError("connection failed")
            yield

    test_datasource.db_type = "mysql"
    test_datasource.host = "127.0.0.1"
    test_datasource.port = 3306
    test_datasource.database_name = "app"
    test_datasource.username = "readonly"
    test_datasource.password_credential_id = "cred"
    test_datasource.ssh_enabled = ssh_enabled
    test_datasource.ssh_host = "127.0.0.1" if ssh_enabled else None
    test_datasource.ssh_username = "tunnel" if ssh_enabled else None
    test_datasource.ssh_password_credential_id = "ssh-cred" if ssh_enabled else None
    test_datasource.ssl_enabled = ssl_enabled
    test_datasource.ssl_verify_identity = False
    db_session.commit()

    with pytest.raises(SchemaInspectionError) as exc_info:
        CatalogIntrospector(
            connection_factory=ConnectionFailureFactory(),
        ).inspect_catalog(db_session, test_datasource.id)

    assert exc_info.value.code == expected_code


def test_duckdb_catalog_uses_batched_metadata_queries(
    db_session,
    test_datasource,
    tmp_path,
) -> None:
    duckdb = pytest.importorskip("duckdb")
    database_path = tmp_path / "catalog.duckdb"
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY, name VARCHAR)")
        connection.execute(
            "CREATE TABLE child("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER REFERENCES parent(id)"
            ")"
        )
    finally:
        connection.close()

    datasource = DataSource(
        project_id=test_datasource.project_id,
        name="duckdb-catalog",
        db_type="duckdb",
        host="",
        port=1,
        database_name=str(database_path),
        username="",
        env="dev",
    )
    db_session.add(datasource)
    db_session.commit()

    inventory = CatalogIntrospector().inspect_catalog(db_session, datasource.id)

    assert [table.table_name for table in inventory.tables] == ["child", "parent"]
    child = inventory.tables[0]
    assert child.columns[0].is_primary_key is True
    assert child.foreign_keys[0].referenced_table == "parent"


def test_duckdb_memory_datasource_is_not_authoritative(
    db_session,
    test_datasource,
) -> None:
    datasource = DataSource(
        project_id=test_datasource.project_id,
        name="duckdb-memory",
        db_type="duckdb",
        host="",
        port=1,
        database_name=":memory:",
        username="",
        env="dev",
    )
    db_session.add(datasource)
    db_session.commit()

    with pytest.raises(SchemaInspectionError) as exc_info:
        CatalogIntrospector().inspect_catalog(db_session, datasource.id)

    assert exc_info.value.code == SchemaInspectionErrorCode.DUCKDB_MEMORY_UNSUPPORTED
