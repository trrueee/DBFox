from __future__ import annotations

import sys

from sqlalchemy.orm import Session

from engine.errors import DBFoxError
from engine.models import DataSource

TEST_DATA_ALLOWED_ENVS = frozenset({"dev", "test", ""})


def validate_row_count(row_count: int) -> None:
    if row_count < 1:
        raise DBFoxError(
            message=f"单次生成行数必须至少为 1，当前请求 {row_count} 行。",
            code="ROW_COUNT_INVALID",
        )
    if row_count > 10_000:
        raise DBFoxError(
            message=f"单次生成行数不能超过 10000，当前请求 {row_count} 行。",
            code="ROW_COUNT_TOO_LARGE",
        )


def require_writable_test_datasource(db: Session, datasource_id: str) -> DataSource:
    if getattr(sys, "frozen", False):
        raise DBFoxError(message="测试数据写入在打包构建中不可用。", code="TEST_DATA_DENIED")

    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise DBFoxError(message="数据源不存在", code="DATASOURCE_NOT_FOUND")

    ds_env = (datasource.env or "").lower()
    if ds_env not in TEST_DATA_ALLOWED_ENVS:
        raise DBFoxError(
            message=f"测试数据写入仅允许 dev/test 环境数据源，当前数据源环境为 '{ds_env}'。",
            code="TEST_DATA_DENIED",
        )
    return datasource
