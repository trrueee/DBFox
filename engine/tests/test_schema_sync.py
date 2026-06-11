"""Schema sync tests — 对应第一版.md Section 18.2"""
import uuid
import pytest
import engine.schema_sync as schema_sync_module
from engine.schema_sync import sync_schema, build_er_diagram_data
from engine.models import DataSource, SchemaTable, SchemaColumn


def test_sync_tables(db_session, demo_datasource) -> None:
    result = sync_schema(db_session, demo_datasource.id)
    assert result["ok"] is True
    tables = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id
    ).all()
    assert len(tables) == 20




def test_sync_columns(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    columns = db_session.query(SchemaColumn).join(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id
    ).all()
    assert len(columns) > 0
    column_names = {c.column_name for c in columns}
    assert "id" in column_names
    assert "username" in column_names
    assert "email" in column_names


def test_sync_primary_keys(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    users_table = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id,
        SchemaTable.table_name == "users",
    ).first()
    assert users_table is not None
    pk_col = db_session.query(SchemaColumn).filter(
        SchemaColumn.table_id == users_table.id,
        SchemaColumn.column_name == "id",
    ).first()
    assert pk_col is not None
    assert bool(pk_col.is_primary_key) is True


def test_sync_foreign_keys(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    products_table = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id,
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
        SchemaTable.data_source_id == demo_datasource.id,
        SchemaTable.table_name == "categories",
    ).first()
    assert fk_col.foreign_table_id == categories_table.id


def test_table_comment(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    users_table = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id,
        SchemaTable.table_name == "users",
    ).first()
    assert users_table.table_comment is None  # SQLite tables have no comments by default


def test_column_comment(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    users_table = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id,
        SchemaTable.table_name == "users",
    ).first()
    username_col = db_session.query(SchemaColumn).filter(
        SchemaColumn.table_id == users_table.id,
        SchemaColumn.column_name == "username",
    ).first()
    assert username_col.column_comment is None  # SQLite columns have no comments by default


def test_sync_idempotent(db_session, demo_datasource) -> None:
    # First sync
    sync_schema(db_session, demo_datasource.id)
    initial_count = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id
    ).count()
    initial_col_count = db_session.query(SchemaColumn).join(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id
    ).count()

    # Second sync — should clear old data and re-insert, not duplicate
    sync_schema(db_session, demo_datasource.id)
    second_count = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id
    ).count()
    second_col_count = db_session.query(SchemaColumn).join(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id
    ).count()

    assert second_count == initial_count
    assert second_col_count == initial_col_count


def test_sync_failure_status(db_session) -> None:
    # Use a non-existent datasource id
    with pytest.raises(ValueError, match="Data source not found"):
        sync_schema(db_session, str(uuid.uuid4()))


def test_sync_failure_preserves_existing_schema(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)
    initial_table_count = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id
    ).count()
    initial_column_count = db_session.query(SchemaColumn).join(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id
    ).count()

    def _failing_snapshot(ds, ds_id):
        raise ValueError("Simulated schema sync failure")

    monkeypatch.setattr(schema_sync_module, "_build_sqlite_schema_snapshot", _failing_snapshot)

    with pytest.raises(ValueError, match="Schema sync failed"):
        sync_schema(db_session, demo_datasource.id)

    assert db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id
    ).count() == initial_table_count
    assert db_session.query(SchemaColumn).join(SchemaTable).filter(
        SchemaTable.data_source_id == demo_datasource.id
    ).count() == initial_column_count

    db_session.refresh(demo_datasource)
    assert demo_datasource.last_sync_status == "failed"


def test_cascade_delete_datasource(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    ds_id = demo_datasource.id

    # Verify tables and columns exist
    assert db_session.query(SchemaTable).filter(SchemaTable.data_source_id == ds_id).count() == 20
    assert db_session.query(SchemaColumn).join(SchemaTable).filter(
        SchemaTable.data_source_id == ds_id
    ).count() > 0

    # Delete datasource
    db_session.delete(demo_datasource)
    db_session.commit()

    # Verify cascade — no orphaned schema data
    assert db_session.query(SchemaTable).filter(SchemaTable.data_source_id == ds_id).count() == 0
    assert db_session.query(SchemaColumn).join(SchemaTable).filter(
        SchemaTable.data_source_id == ds_id
    ).count() == 0
