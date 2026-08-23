from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from engine.errors import ToolInputError
from engine.models import DataSource, SchemaColumn, SchemaTable
from dlcs.dbfox_data.backend.sensitivity import is_sensitive_name

DEFAULT_PREVIEW_ROWS = 10


def _looks_sensitive(column_name: str) -> bool:
    return is_sensitive_name(column_name)


def _datasource(db: Session, datasource_id: str) -> DataSource:
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if ds is None:
        raise ValueError("Data source not found")
    return ds


def _catalog_table(db: Session, datasource_id: str, name: str) -> SchemaTable | None:
    parts = [part.strip() for part in name.split(".") if part.strip()]
    if len(parts) == 1:
        filters = [SchemaTable.table_name == parts[0]]
    elif len(parts) == 2:
        filters = [
            SchemaTable.table_schema == parts[0],
            SchemaTable.table_name == parts[1],
        ]
    else:
        raise ToolInputError(f"Invalid catalog table name: {name}")

    matches = (
        db.query(SchemaTable)
        .filter(SchemaTable.data_source_id == datasource_id, *filters)
        .order_by(SchemaTable.table_schema, SchemaTable.table_name, SchemaTable.id)
        .limit(2)
        .all()
    )
    if len(matches) > 1:
        raise ToolInputError(
            f"Ambiguous table name: {name}. Use the qualified_name returned by schema_list."
        )
    return matches[0] if matches else None


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
