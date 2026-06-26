from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from engine.errors import DBFoxError
from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.test_data.fk_resolver import resolve_foreign_key_mappings
from engine.test_data.generator import (
    generate_random_address,
    generate_random_email,
    generate_random_name,
    generate_random_phone,
    generate_rows,
    get_field_type_hint,
)
from engine.test_data.policy import validate_row_count
from engine.test_data import sqlite_insert_service

logger = logging.getLogger("dbfox.test_data")


def generate_smart_test_data(
    db: Session,
    datasource_id: str,
    table_name: str,
    row_count: int = 10,
    language: str = "zh",
) -> dict[str, Any]:
    start_time = datetime.now()
    validate_row_count(row_count)

    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise DBFoxError(message="数据源不存在", code="DATASOURCE_NOT_FOUND")

    table = db.query(SchemaTable).filter(
        SchemaTable.data_source_id == datasource_id,
        SchemaTable.table_name == table_name,
    ).first()
    if not table:
        raise DBFoxError(message=f"表 `{table_name}` 尚未同步，请先同步 Schema", code="TABLE_NOT_FOUND")

    columns: list[SchemaColumn] = list(table.columns)
    if not columns:
        raise DBFoxError(message=f"表 `{table_name}` 没有定义字段，请重新检查表结构", code="NO_COLUMNS")

    try:
        fk_mappings = resolve_foreign_key_mappings(db, datasource_id, columns)
        generated_rows = generate_rows(columns, row_count, language, fk_mappings)
        statements = sqlite_insert_service.build_insert_statements(table_name, generated_rows)
        sqlite_insert_service.execute_test_data_inserts(db, datasource_id, statements)
        inserted_count = len(statements)
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        table.row_count_estimate = (table.row_count_estimate or 0) + inserted_count  # type: ignore[assignment]
        db.commit()
        return {
            "success": True,
            "tableName": table_name,
            "insertedRows": inserted_count,
            "latencyMs": latency_ms,
            "message": f"成功为表 `{table_name}` 智能注入 {inserted_count} 条高保真测试数据！",
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to insert mockup test data")
        if isinstance(exc, DBFoxError):
            raise
        raise DBFoxError(
            message=f"智能测试数据生成或写入失败: {str(exc)}",
            code="TEST_DATA_GENERATION_FAILED",
        ) from exc


__all__ = [
    "generate_random_address",
    "generate_random_email",
    "generate_random_name",
    "generate_random_phone",
    "generate_smart_test_data",
    "get_field_type_hint",
]
