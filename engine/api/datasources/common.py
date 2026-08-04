from __future__ import annotations

from datetime import datetime
from typing import Any

from engine.datasource import datasource_connection_dict
from engine.json_codec import dumps
from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.schemas.datasource import DataSourceResponse
from engine.app.safe_errors import FixedErrorCode


def datasource_to_dict(ds: DataSource) -> dict[str, Any]:
    return DataSourceResponse.model_validate(ds).model_dump(mode="json")


def schema_table_to_dict(table: SchemaTable) -> dict[str, Any]:
    return {
        "id": table.id,
        "table_schema": table.table_schema or "",
        "table_name": table.table_name,
        "table_comment": table.table_comment or "",
        "table_type": table.table_type,
        "row_count_estimate": table.row_count_estimate,
        "columns_count": len(table.columns),
        "module_tag": table.table_schema or None,
        "ai_description": table.ai_description or "",
        "semantic_tags": table.semantic_tags or "",
        "business_terms": table.business_terms or "",
        "ai_confidence": table.ai_confidence,
        "subject_area": table.subject_area or "",
    }


def schema_column_to_dict(column: SchemaColumn) -> dict[str, Any]:
    return {
        "id": column.id,
        "column_name": column.column_name,
        "data_type": column.data_type,
        "column_type": column.column_type,
        "is_nullable": bool(column.is_nullable),
        "column_default": column.column_default or "",
        "column_comment": column.column_comment or "",
        "is_primary_key": bool(column.is_primary_key),
        "is_foreign_key": bool(column.is_foreign_key),
        "foreign_table_id": column.foreign_table_id,
        "foreign_column_id": column.foreign_column_id,
        "ai_description": column.ai_description or "",
        "semantic_tags": column.semantic_tags or "",
        "business_terms": column.business_terms or "",
        "ai_confidence": column.ai_confidence,
    }


def datasource_to_health_config(ds: DataSource) -> dict[str, Any]:
    """Return opaque metadata; the factory resolves secrets only at driver use."""
    return datasource_connection_dict(ds)


def persist_health_success(
    ds: DataSource,
    result: dict[str, Any],
    latency_ms: int,
    checked_at: datetime,
) -> None:
    warnings = [str(item) for item in result.get("warnings", [])]
    setattr(ds, "last_test_at", checked_at)
    setattr(ds, "last_test_status", "success")
    setattr(ds, "last_test_error", None)
    setattr(ds, "last_test_latency_ms", latency_ms)
    setattr(ds, "last_test_readonly", bool(result.get("readonly", False)))
    setattr(ds, "last_test_server_version", str(result.get("serverVersion") or ""))
    setattr(ds, "last_test_tables_count", int(result.get("tablesCount") or 0))
    setattr(ds, "last_test_warnings", dumps(warnings))


def persist_health_failure(
    ds: DataSource,
    error_code: FixedErrorCode,
    latency_ms: int,
    checked_at: datetime,
) -> None:
    setattr(ds, "last_test_at", checked_at)
    setattr(ds, "last_test_status", "failed")
    setattr(ds, "last_test_error", error_code.value)
    setattr(ds, "last_test_latency_ms", latency_ms)
    setattr(ds, "last_test_readonly", None)
    setattr(ds, "last_test_server_version", None)
    setattr(ds, "last_test_tables_count", None)
    setattr(ds, "last_test_warnings", dumps([]))


def set_model_attr(obj: object, attr: str, value: Any) -> None:
    setattr(obj, attr, value)
