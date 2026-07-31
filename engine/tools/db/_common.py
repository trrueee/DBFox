from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.policy.sensitivity import _SENSITIVE_FALLBACK

MAX_PREVIEW_ROWS = 20
DEFAULT_PREVIEW_ROWS = 10


def _looks_sensitive(column_name: str) -> bool:
    return bool(_SENSITIVE_FALLBACK.search(column_name))


def _datasource(db: Session, datasource_id: str) -> DataSource:
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if ds is None:
        raise ValueError("Data source not found")
    return ds


def _catalog_table(db: Session, datasource_id: str, name: str) -> SchemaTable | None:
    return (
        db.query(SchemaTable)
        .filter(
            SchemaTable.data_source_id == datasource_id,
            SchemaTable.table_name == name,
        )
        .first()
    )


def _ordered_columns(table: SchemaTable) -> list[SchemaColumn]:
    return sorted(
        list(table.columns or []),
        key=lambda c: (c.ordinal_position or 10_000, str(c.column_name)),
    )


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list):
        return [str(s).strip() for s in value if str(s).strip()]
    return []


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(value, hi))
