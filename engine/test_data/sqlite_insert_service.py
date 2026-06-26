from __future__ import annotations

import sqlite3
from typing import Any, Sequence, Tuple

from sqlalchemy.orm import Session

from engine.errors import DBFoxError
from engine.test_data.policy import require_writable_test_datasource

InsertStatement = Tuple[str, dict[str, Any]]


def build_insert_statements(table_name: str, rows: list[dict[str, Any]]) -> list[InsertStatement]:
    statements: list[InsertStatement] = []
    for row in rows:
        cols = list(row.keys())
        placeholders = ", ".join(f":{column}" for column in cols)
        cols_quoted = ", ".join(f"`{column}`" for column in cols)
        insert_sql = f"INSERT INTO `{table_name}` ({cols_quoted}) VALUES ({placeholders})"
        statements.append((insert_sql, row))
    return statements


def execute_test_data_inserts(
    db: Session,
    datasource_id: str,
    statements: Sequence[InsertStatement],
) -> None:
    datasource = require_writable_test_datasource(db, datasource_id)
    db_type = (datasource.db_type or "mysql").lower()
    if db_type == "postgresql":
        raise DBFoxError(message="测试数据生成暂不支持 PostgreSQL。", code="TEST_DATA_UNSUPPORTED")
    if db_type != "sqlite":
        raise DBFoxError(message="测试数据生成暂不支持 MySQL，请使用 SQLite 数据源。", code="TEST_DATA_UNSUPPORTED")

    db_path = str(datasource.database_name or "")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("BEGIN")
        for insert_sql, params in statements:
            conn.execute(insert_sql, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
