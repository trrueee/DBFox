from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from engine import schemas as engine_schemas
from engine.errors import DBFoxError
from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.test_data import generate_smart_test_data


def test_generate_smart_test_data_uses_dbfox_error_code_message_contract(db_session, test_datasource) -> None:
    with pytest.raises(DBFoxError) as exc_info:
        generate_smart_test_data(
            db=db_session,
            datasource_id=test_datasource.id,
            table_name="users",
            row_count=10_001,
        )

    assert exc_info.value.code == "ROW_COUNT_TOO_LARGE"
    assert "单次生成行数不能超过 10000" in exc_info.value.message


@pytest.mark.parametrize("row_count", [-1, 0, 10_001])
def test_test_data_generate_request_rejects_out_of_range_row_count(row_count: int) -> None:
    with pytest.raises(ValidationError):
        engine_schemas.TestDataGenerateRequest(
            datasource_id="ds-1",
            table_name="users",
            row_count=row_count,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("datasource_id", ""),
        ("datasource_id", " " * 3),
        ("datasource_id", "d" * 129),
        ("table_name", ""),
        ("table_name", " " * 3),
        ("table_name", "t" * 257),
    ],
)
def test_test_data_generate_request_rejects_blank_or_oversized_identifiers(
    field_name: str,
    value: str,
) -> None:
    payload = {
        "datasource_id": "ds-1",
        "table_name": "users",
        "row_count": 10,
    }
    payload[field_name] = value

    with pytest.raises(ValidationError):
        engine_schemas.TestDataGenerateRequest(**payload)


def test_test_data_generate_request_rejects_unsupported_language() -> None:
    with pytest.raises(ValidationError):
        engine_schemas.TestDataGenerateRequest(
            datasource_id="ds-1",
            table_name="users",
            row_count=10,
            language="javascript",
        )


def test_generate_smart_test_data_rolls_back_target_sqlite_batch_on_failure(
    db_session,
    tmp_path,
    monkeypatch,
) -> None:
    sqlite_path = tmp_path / "target.db"
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    ds = DataSource(
        id="ds-test-data-rollback",
        name="rollback-target",
        host="",
        port=0,
        database_name=str(sqlite_path),
        username="",
        db_type="sqlite",
        connection_generation=1,
        env="dev",
        status="active",
    )
    table = SchemaTable(
        id="tbl-test-data-rollback-users",
        data_source_id=ds.id,
        table_schema="main",
        table_name="users",
        table_type="table",
        row_count_estimate=0,
    )
    columns = [
        SchemaColumn(
            id="col-test-data-rollback-id",
            table_id=table.id,
            column_name="id",
            data_type="INTEGER",
            column_type="INTEGER",
            is_primary_key=True,
            is_nullable=False,
            ordinal_position=1,
        ),
        SchemaColumn(
            id="col-test-data-rollback-email",
            table_id=table.id,
            column_name="email",
            data_type="TEXT",
            column_type="TEXT",
            is_nullable=False,
            ordinal_position=2,
        ),
        SchemaColumn(
            id="col-test-data-rollback-created-at",
            table_id=table.id,
            column_name="created_at",
            data_type="TEXT",
            column_type="TEXT",
            is_nullable=False,
            ordinal_position=3,
        ),
    ]
    db_session.add_all([ds, table, *columns])
    db_session.commit()

    monkeypatch.setattr("engine.test_data.generator.generate_random_email", lambda *_args: "same@example.test")

    with pytest.raises(DBFoxError) as exc_info:
        generate_smart_test_data(db_session, ds.id, "users", row_count=2)

    assert exc_info.value.code == "TEST_DATA_GENERATION_FAILED"
    with sqlite3.connect(sqlite_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0

    db_session.refresh(table)
    assert table.row_count_estimate == 0
