"""db_preview — safe live data preview from a single table."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from dlcs.dbfox_data.backend.tool_contracts import MAX_PREVIEW_ROWS
from engine.errors import ToolInputError
from engine.models import SchemaColumn
from engine.sql.dialect_context import load_dialect_context
from engine.sql.executor import execute_query
from engine.sql.safety.service import SqlSafetyService
from engine.tools.db._common import (
    _catalog_table,
    _clamp,
    _datasource,
    _looks_sensitive,
    _ordered_columns,
    _string_list,
)


def db_preview(
    db: Session,
    datasource_id: str,
    *,
    table: str,
    columns: list[str] | None = None,
    limit: int = 10,
    where: dict[str, Any] | None = None,
    order_by: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Preview a small, safe sample of live data from one table.

    Safety: column whitelist, LIMIT ≤ 20, TrustGate, timeout, redaction.
    """
    if where is not None and not isinstance(where, dict):
        raise ToolInputError("WHERE must be a structured filter object.")
    if order_by is not None and not isinstance(order_by, (dict, list)):
        raise ToolInputError("ORDER BY must be a structured order object or list.")

    start = time.perf_counter()
    table_name = table.strip()
    if not table_name:
        raise ToolInputError("A non-empty catalog table name is required.")

    catalog_table = _catalog_table(db, datasource_id, table_name)
    if catalog_table is None:
        raise ToolInputError(
            f"Table not found in the current catalog: {table_name}. "
            "Use schema_list or schema_search and retry with its qualified_name."
        )

    available = {str(c.column_name): c for c in _ordered_columns(catalog_table)}
    args: dict[str, Any] = {"table": table_name, "limit": limit}
    if columns:
        args["columns"] = columns
    if where:
        args["where"] = where
    if order_by:
        args["order_by"] = order_by

    requested = _resolve_preview_columns(args, available)
    requested_for_validation = [*requested, *_structured_column_refs(where), *_structured_order_refs(order_by)]
    unknown = [n for n in requested if n not in available]
    unknown.extend(n for n in requested_for_validation if n not in available and n not in unknown)
    if unknown:
        available_names = ", ".join(list(available)[:30])
        raise ToolInputError(
            f"Column(s) not found in {table_name}: {', '.join(unknown)}. "
            f"Available columns: {available_names}."
        )

    requested_limit = _clamp(int(limit), 1, MAX_PREVIEW_ROWS)
    dialect = _resolve_dialect(db, datasource_id)
    sql, parameters = _build_preview_sql(
        str(catalog_table.table_name),
        requested,
        requested_limit,
        args,
        dialect,
        schema_name=str(catalog_table.table_schema or "") or None,
        catalog_validated_identifiers=True,
    )

    ctx = load_dialect_context(db, datasource_id)
    decision = SqlSafetyService(db).build_execution_decision(
        sql, ctx, policy="table_preview", parameters=parameters
    )
    result = execute_query(
        db,
        datasource_id,
        sql,
        question=f"Preview table {table_name}",
        safety_decision=decision,
        safety_policy="table_preview",
        parameters=parameters,
        redact=True,
    )

    rows = result.get("rows") or []
    safe_sql = str((result.get("safetyDecision") or {}).get("safe_sql") or result.get("safe_sql") or sql)

    return {
        "table": table_name,
        "columns": requested,
        "returned_rows": len(rows),
        "limit_applied": requested_limit,
        "rows": rows,
        "safe_sql": safe_sql,
        "parameters": parameters,
        "truncated": bool(result.get("truncated")),
        "warnings": result.get("warnings") or [],
        "column_summaries": [_column_summary_preview(available[n]) for n in requested],
        "audit": {
            "readonly_checked": True,
            "limit_enforced": True,
            "history_id": result.get("historyId"),
            "execution_id": result.get("executionId"),
        },
        "latency_ms": int((time.perf_counter() - start) * 1000),
    }


# ===================================================================
# db_preview helpers
# ===================================================================


def _resolve_dialect(db: Session, datasource_id: str) -> str:
    ds = _datasource(db, datasource_id)
    return (ds.db_type or "mysql").lower()


def _resolve_preview_columns(args: dict[str, Any], available: dict[str, SchemaColumn]) -> list[str]:
    requested = _string_list(args.get("columns"))
    if not requested:
        safe = [n for n, c in available.items() if not _looks_sensitive(n)]
        return safe[:8]
    return requested


def _build_preview_sql(
    table_name: str,
    columns: list[str],
    limit: int,
    args: dict[str, Any],
    dialect: str,
    *,
    schema_name: str | None = None,
    catalog_validated_identifiers: bool = False,
) -> tuple[str, dict[str, Any]]:
    from dlcs.dbfox_data.backend.sql.builder import build_select
    return build_select(
        table=table_name,
        columns=columns,
        where=args.get("where"),
        order=args.get("order_by") or args.get("order"),
        limit=limit,
        dialect=dialect,
        catalog_validated_identifiers=catalog_validated_identifiers,
        table_schema=schema_name,
    )


def _structured_column_refs(where: dict[str, Any] | None) -> list[str]:
    if not isinstance(where, dict):
        return []
    column = str(where.get("column") or "").strip()
    return [column] if column else []


def _structured_order_refs(order_by: dict[str, Any] | list[dict[str, Any]] | None) -> list[str]:
    if isinstance(order_by, dict):
        column = str(order_by.get("column") or "").strip()
        return [column] if column else []
    if isinstance(order_by, list):
        columns: list[str] = []
        for item in order_by:
            if not isinstance(item, dict):
                continue
            column = str(item.get("column") or "").strip()
            if column:
                columns.append(column)
        return columns
    return []


def _column_summary_preview(col: SchemaColumn) -> dict[str, Any]:
    return {
        "name": str(col.column_name),
        "type": str(col.column_type or col.data_type or ""),
        "nullable": bool(col.is_nullable),
        "sensitive": _looks_sensitive(str(col.column_name)),
    }


# ===================================================================
# Shared helpers
# ===================================================================


def _infer_column_types(result: dict[str, Any]) -> list[str]:
    """Best-effort column type extraction from execution result."""
    rows = result.get("rows") or []
    columns = result.get("columns") or []
    if not rows or not columns:
        return []
    first = rows[0]
    types: list[str] = []
    for col in columns:
        val = first.get(col) if isinstance(first, dict) else None
        if val is None:
            types.append("unknown")
        elif isinstance(val, bool):
            types.append("boolean")
        elif isinstance(val, int):
            types.append("integer")
        elif isinstance(val, float):
            types.append("float")
        elif isinstance(val, bytes):
            types.append("binary")
        else:
            types.append("string")
    return types
