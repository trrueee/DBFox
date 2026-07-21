"""Regression coverage for authoritative schema catalog synchronization."""
from __future__ import annotations

import pytest

from engine.connectivity.factory import ConnectionFactory
from engine.environment.authoritative_inventory import (
    AuthoritativeInventory,
    SchemaInspectionError,
    SchemaInspectionErrorCode,
)
from engine.environment.inventory import SchemaInventory
from engine.environment.schema_catalog_sync import SchemaCatalogSync
from engine.environment.schema_introspector import SchemaIntrospector
from engine.models import SchemaTable
from engine.schema_sync import sync_schema


def _catalog_table_names(db_session, datasource_id: str) -> list[str]:
    return [
        str(row.table_name)
        for row in (
            db_session.query(SchemaTable)
            .filter(SchemaTable.data_source_id == datasource_id)
            .order_by(SchemaTable.table_name)
            .all()
        )
    ]


def test_failed_mysql_inspection_never_deletes_existing_catalog(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection failure must not be translated into an empty snapshot."""
    sync_schema(db_session, test_datasource.id, ai_enrich=False)
    expected_catalog = _catalog_table_names(db_session, test_datasource.id)
    assert expected_catalog

    test_datasource.db_type = "mysql"
    test_datasource.host = "127.0.0.1"
    test_datasource.port = 3306
    test_datasource.database_name = "catalog_preservation"
    test_datasource.username = "readonly"
    test_datasource.password_credential_id = "cred_datasource_password"
    db_session.commit()

    def raise_connect_timeout(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("simulated MySQL connection timeout")

    monkeypatch.setattr(ConnectionFactory, "_pooled_connection", raise_connect_timeout)

    with pytest.raises(SchemaInspectionError) as exc_info:
        SchemaCatalogSync().sync(db_session, test_datasource.id)

    assert exc_info.value.datasource_id == test_datasource.id
    assert exc_info.value.code == SchemaInspectionErrorCode.CONNECTION_FAILED
    assert _catalog_table_names(db_session, test_datasource.id) == expected_catalog
    db_session.refresh(test_datasource)
    assert test_datasource.last_sync_status == "failed"


def test_catalog_sync_rejects_non_authoritative_inventory_without_mutation(
    db_session,
    test_datasource,
) -> None:
    sync_schema(db_session, test_datasource.id, ai_enrich=False)
    expected_catalog = _catalog_table_names(db_session, test_datasource.id)

    with pytest.raises(TypeError, match="AuthoritativeInventory"):
        SchemaCatalogSync().sync_authoritative(
            db_session,
            SchemaInventory(datasource_id=test_datasource.id, dialect="sqlite"),  # type: ignore[arg-type]
        )

    assert _catalog_table_names(db_session, test_datasource.id) == expected_catalog


def test_successful_authoritative_empty_inventory_can_remove_obsolete_catalog(
    db_session,
    test_datasource,
) -> None:
    sync_schema(db_session, test_datasource.id, ai_enrich=False)
    assert _catalog_table_names(db_session, test_datasource.id)

    empty_inventory = AuthoritativeInventory.from_completed_inventory(
        SchemaInventory(datasource_id=test_datasource.id, dialect="sqlite")
    )
    result = SchemaCatalogSync().sync_authoritative(db_session, empty_inventory)

    assert result.synced is True
    assert result.tables_removed > 0
    assert _catalog_table_names(db_session, test_datasource.id) == []


def test_authoritative_catalog_failure_rolls_back_all_reconciliation_changes(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_schema(db_session, test_datasource.id, ai_enrich=False)
    expected_catalog = _catalog_table_names(db_session, test_datasource.id)
    empty_inventory = AuthoritativeInventory.from_completed_inventory(
        SchemaInventory(datasource_id=test_datasource.id, dialect="sqlite")
    )

    def fail_search_rebuild(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected catalog rebuild failure")

    monkeypatch.setattr(
        "engine.environment.schema_catalog_sync.rebuild_search_docs",
        fail_search_rebuild,
    )

    with pytest.raises(RuntimeError, match="injected catalog rebuild failure"):
        SchemaCatalogSync().sync_authoritative(db_session, empty_inventory)

    assert _catalog_table_names(db_session, test_datasource.id) == expected_catalog
