from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from engine.errors import DBFoxError
from engine.models import SchemaColumn, SchemaTable
from engine.sql.dialect_context import DialectContext
from engine.sql.executor import execute_query
from engine.sql.safety.service import SqlSafetyService

logger = logging.getLogger("dbfox.test_data.fk_resolver")


def resolve_foreign_key_mappings(
    db: Session,
    datasource_id: str,
    columns: list[SchemaColumn],
) -> dict[str, list[Any]]:
    fk_mappings: dict[str, list[Any]] = {}

    for column in columns:
        if not column.is_foreign_key or not column.foreign_table_id:
            continue

        parent_table = db.query(SchemaTable).filter(SchemaTable.id == column.foreign_table_id).first()
        if not parent_table:
            continue

        parent_column_name = "id"
        if column.foreign_column_id:
            parent_col_obj = db.query(SchemaColumn).filter(SchemaColumn.id == column.foreign_column_id).first()
            if parent_col_obj:
                parent_column_name = str(parent_col_obj.column_name)

        try:
            logger.info(
                "Querying parent keys from table %s col %s",
                parent_table.table_name,
                parent_column_name,
            )
            parent_query_sql = f"SELECT `{parent_column_name}` FROM `{parent_table.table_name}` LIMIT 200"
            ctx = DialectContext.from_datasource_id(db, datasource_id)
            decision = SqlSafetyService(db).build_execution_decision(parent_query_sql, ctx, policy="readonly")
            parent_res = execute_query(
                db,
                datasource_id,
                parent_query_sql,
                safety_decision=decision,
                safety_policy="readonly",
            )

            if parent_res["success"] and parent_res["rows"]:
                parent_ids = [row[parent_column_name] for row in parent_res["rows"]]
                fk_mappings[str(column.column_name)] = parent_ids
                continue

            raise DBFoxError(
                message=f"关联的外键主表 `{parent_table.table_name}` 尚无数据！请先为其生成或录入数据，再为此子表造数据。",
                code="REFERENTIAL_INTEGRITY_VIOLATION",
            )
        except DBFoxError:
            raise
        except Exception as exc:
            logger.exception("Failed to query parent keys for FK column %s", column.column_name)
            raise DBFoxError(
                message=f"无法查询外键关联表 `{parent_table.table_name}` 的数据：{exc}",
                code="FK_RESOLUTION_FAILED",
            ) from exc

    return fk_mappings
