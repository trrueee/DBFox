"""Schema sync tests — 对应第一版.md Section 18.2"""
import uuid
import pytest
import engine.schema_sync as schema_sync_module
from engine.llm.config import LlmConfig
from engine.environment.inventory import ColumnInventory, SchemaInventory, TableInventory
from engine.environment.schema_catalog_sync import SchemaCatalogSync
from engine.schema_sync import sync_schema, build_er_diagram_data
from engine.models import DataSource, SchemaTable, SchemaColumn


def test_sync_tables(db_session, test_datasource) -> None:
    result = sync_schema(db_session, test_datasource.id)
    assert result["ok"] is True
    tables = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id
    ).all()
    assert len(tables) == 20




def test_sync_columns(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    columns = db_session.query(SchemaColumn).join(SchemaTable, SchemaColumn.table_id == SchemaTable.id).filter(
        SchemaTable.data_source_id == test_datasource.id
    ).all()
    assert len(columns) > 0
    column_names = {c.column_name for c in columns}
    assert "id" in column_names
    assert "username" in column_names
    assert "email" in column_names


def test_sync_primary_keys(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    users_table = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id,
        SchemaTable.table_name == "users",
    ).first()
    assert users_table is not None
    pk_col = db_session.query(SchemaColumn).filter(
        SchemaColumn.table_id == users_table.id,
        SchemaColumn.column_name == "id",
    ).first()
    assert pk_col is not None
    assert bool(pk_col.is_primary_key) is True


def test_sync_foreign_keys(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    products_table = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id,
        SchemaTable.table_name == "products",
    ).first()
    assert products_table is not None
    fk_col = db_session.query(SchemaColumn).filter(
        SchemaColumn.table_id == products_table.id,
        SchemaColumn.column_name == "category_id",
    ).first()
    assert fk_col is not None
    assert bool(fk_col.is_foreign_key) is True
    # verify FK points to categories table
    categories_table = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id,
        SchemaTable.table_name == "categories",
    ).first()
    assert fk_col.foreign_table_id == categories_table.id


def test_table_comment(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    users_table = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id,
        SchemaTable.table_name == "users",
    ).first()
    assert users_table.table_comment is None  # SQLite tables have no comments by default


def test_column_comment(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    users_table = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id,
        SchemaTable.table_name == "users",
    ).first()
    username_col = db_session.query(SchemaColumn).filter(
        SchemaColumn.table_id == users_table.id,
        SchemaColumn.column_name == "username",
    ).first()
    assert username_col.column_comment is None  # SQLite columns have no comments by default


def test_sync_idempotent(db_session, test_datasource) -> None:
    # First sync
    sync_schema(db_session, test_datasource.id)
    initial_count = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id
    ).count()
    initial_col_count = db_session.query(SchemaColumn).join(SchemaTable, SchemaColumn.table_id == SchemaTable.id).filter(
        SchemaTable.data_source_id == test_datasource.id
    ).count()

    # Second sync — should clear old data and re-insert, not duplicate
    sync_schema(db_session, test_datasource.id)
    second_count = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id
    ).count()
    second_col_count = db_session.query(SchemaColumn).join(SchemaTable, SchemaColumn.table_id == SchemaTable.id).filter(
        SchemaTable.data_source_id == test_datasource.id
    ).count()

    assert second_count == initial_count
    assert second_col_count == initial_col_count


def test_catalog_sync_preserves_same_table_name_in_different_schemas(db_session, test_datasource) -> None:
    syncer = SchemaCatalogSync()
    initial_inventory = SchemaInventory(
        datasource_id=test_datasource.id,
        dialect="postgresql",
        database_name="demo",
        tables=[
            TableInventory(
                table_schema="tenant_a",
                table_name="orders",
                columns=[
                    ColumnInventory(column_name="id", data_type="integer", is_nullable=False, is_primary_key=True),
                    ColumnInventory(column_name="amount", data_type="numeric"),
                ],
            ),
            TableInventory(
                table_schema="tenant_b",
                table_name="orders",
                columns=[
                    ColumnInventory(column_name="id", data_type="integer", is_nullable=False, is_primary_key=True),
                    ColumnInventory(column_name="status", data_type="text"),
                ],
            ),
        ],
    )
    syncer.sync_inventory(db_session, test_datasource.id, initial_inventory)

    updated_inventory = SchemaInventory(
        datasource_id=test_datasource.id,
        dialect="postgresql",
        database_name="demo",
        tables=[
            TableInventory(
                table_schema="tenant_a",
                table_name="orders",
                columns=[
                    ColumnInventory(column_name="id", data_type="integer", is_nullable=False, is_primary_key=True),
                    ColumnInventory(column_name="amount_cents", data_type="integer"),
                ],
            ),
            TableInventory(
                table_schema="tenant_b",
                table_name="orders",
                columns=[
                    ColumnInventory(column_name="id", data_type="integer", is_nullable=False, is_primary_key=True),
                    ColumnInventory(column_name="state", data_type="text"),
                ],
            ),
        ],
    )

    syncer.sync_inventory(db_session, test_datasource.id, updated_inventory)

    tables = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id,
        SchemaTable.table_name == "orders",
    ).all()
    columns_by_schema = {
        table.table_schema: {column.column_name for column in table.columns}
        for table in tables
    }

    assert columns_by_schema == {
        "tenant_a": {"id", "amount_cents"},
        "tenant_b": {"id", "state"},
    }


def test_sync_failure_status(db_session) -> None:
    # Use a non-existent datasource id
    with pytest.raises(ValueError, match="Data source not found"):
        sync_schema(db_session, str(uuid.uuid4()))


def test_sync_passes_llm_config_to_ai_enrichment(db_session, test_datasource, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_enrich(db, datasource_id, **kwargs):
        captured["datasource_id"] = datasource_id
        captured["kwargs"] = kwargs
        return {"ai_enriched": True, "enriched_count": 1, "reason": ""}

    monkeypatch.setattr("engine.ai_enrich.ai_enrich_catalog", _fake_enrich)

    result = sync_schema(
        db_session,
        test_datasource.id,
        ai_api_key="sk-test",
        ai_api_base="https://example.test/v1",
        ai_model_name="qwen-plus",
    )

    assert result["ok"] is True
    llm_config = captured["kwargs"].get("llm_config")
    assert isinstance(llm_config, LlmConfig)
    assert llm_config.api_key == "sk-test"
    assert llm_config.api_base == "https://example.test/v1"
    assert llm_config.model_name == "qwen-plus"
    assert llm_config.source == "product"
    assert captured == {
        "datasource_id": test_datasource.id,
        "kwargs": {
            "llm_config": llm_config,
        },
    }


def test_sync_reports_ai_enrichment_warning(db_session, test_datasource, monkeypatch) -> None:
    def _fake_enrich(db, datasource_id, **kwargs):
        return {"ai_enriched": False, "enriched_count": 0, "reason": "missing api key"}

    monkeypatch.setattr("engine.ai_enrich.ai_enrich_catalog", _fake_enrich)

    result = sync_schema(db_session, test_datasource.id, ai_api_key="sk-test")

    assert result["ok"] is True
    assert result["aiEnrich"]["ai_enriched"] is False
    assert result["warnings"] == ["AI 语义打分未完成：missing api key"]


def test_sync_failure_preserves_existing_schema(db_session, test_datasource, monkeypatch) -> None:
    sync_schema(db_session, test_datasource.id)
    initial_table_count = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id
    ).count()
    initial_column_count = db_session.query(SchemaColumn).join(SchemaTable, SchemaColumn.table_id == SchemaTable.id).filter(
        SchemaTable.data_source_id == test_datasource.id
    ).count()

    def _failing_snapshot(db, ds_id):
        raise ValueError("Simulated schema sync failure")

    monkeypatch.setattr("engine.environment.schema_catalog_sync.introspect_datasource", _failing_snapshot)

    with pytest.raises(ValueError, match="Schema sync failed"):
        sync_schema(db_session, test_datasource.id)

    assert db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == test_datasource.id
    ).count() == initial_table_count
    assert db_session.query(SchemaColumn).join(SchemaTable, SchemaColumn.table_id == SchemaTable.id).filter(
        SchemaTable.data_source_id == test_datasource.id
    ).count() == initial_column_count

    db_session.refresh(test_datasource)
    assert test_datasource.last_sync_status == "failed"


def test_cascade_delete_datasource(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    ds_id = test_datasource.id

    # Verify tables and columns exist
    assert db_session.query(SchemaTable).filter(SchemaTable.data_source_id == ds_id).count() == 20
    assert db_session.query(SchemaColumn).join(SchemaTable, SchemaColumn.table_id == SchemaTable.id).filter(
        SchemaTable.data_source_id == ds_id
    ).count() > 0

    # Delete datasource
    db_session.delete(test_datasource)
    db_session.commit()

    # Verify cascade — no orphaned schema data
    assert db_session.query(SchemaTable).filter(SchemaTable.data_source_id == ds_id).count() == 0
    assert db_session.query(SchemaColumn).join(SchemaTable, SchemaColumn.table_id == SchemaTable.id).filter(
        SchemaTable.data_source_id == ds_id
    ).count() == 0
