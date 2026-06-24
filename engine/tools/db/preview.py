"""db.preview — safe live data preview from a single table."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from engine.models import SchemaColumn
from engine.sql.dialect_context import DialectContext
from engine.sql.executor import execute_query
from engine.sql.safety.service import SqlSafetyService
from engine.tools.db._common import (
    DEFAULT_PREVIEW_ROWS,
    MAX_PREVIEW_ROWS,
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
        raise ValueError("WHERE must be a dictionary")
    if order_by is not None and not isinstance(order_by, (dict, list)):
        raise ValueError("ORDER BY must be a dictionary or list of dictionaries")

    start = time.perf_counter()
    table_name = table.strip()
    if not table_name:
        raise ValueError("table is required.")

    catalog_table = _catalog_table(db, datasource_id, table_name)
    if catalog_table is None:
        raise ValueError(f"Unknown table: {table_name}")

    available = {str(c.column_name): c for c in _ordered_columns(catalog_table)}
    args: dict[str, Any] = {"table": table_name, "limit": limit}
    if columns:
        args["columns"] = columns
    if where:
        args["where"] = where
    if order_by:
        args["order_by"] = order_by

    requested = _resolve_preview_columns(args, available)
    unknown = [n for n in requested if n not in available]
    if unknown:
        raise ValueError(f"Unknown column(s) for {table_name}: {', '.join(unknown)}")

    requested_limit = _clamp(int(limit), 1, MAX_PREVIEW_ROWS)
    dialect = _resolve_dialect(db, datasource_id)
    sql = _build_preview_sql(table_name, requested, requested_limit, args, dialect)

    try:
        ctx = DialectContext.from_datasource_id(db, datasource_id)
        decision = SqlSafetyService(db).build_execution_decision(sql, ctx, policy="table_preview")
        result = execute_query(
            db,
            datasource_id,
            sql,
            question=f"Preview table {table_name}",
            safety_decision=decision,
            safety_policy="table_preview",
            redact=True,
        )
    except Exception as exc:
        raise RuntimeError(f"db.preview execution failed: {exc}") from exc

    rows = result.get("rows") or []
    safe_sql = str((result.get("safetyDecision") or {}).get("safe_sql") or result.get("safe_sql") or sql)

    return {
        "table": table_name,
        "columns": requested,
        "returned_rows": len(rows),
        "limit_applied": requested_limit,
        "rows": rows,
        "safe_sql": safe_sql,
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
# db.preview helpers
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
) -> str:
    from engine.sql.builder import build_select
    return build_select(
        table=table_name,
        columns=columns,
        where=args.get("where"),
        order=args.get("order_by") or args.get("order"),
        limit=limit,
        dialect=dialect
    )


def _build_where_clause(where: dict[str, Any], quote: str) -> str | None:
    from engine.sql.builder import build_where_clause
    dialect = "mysql" if quote == "`" else "sqlite" if quote == '"' else "postgres"
    return build_where_clause(where, dialect)


def _build_order_clause(order: dict[str, Any], quote: str) -> str | None:
    from engine.sql.builder import build_order_clause
    dialect = "mysql" if quote == "`" else "sqlite" if quote == '"' else "postgres"
    return build_order_clause(order, dialect)


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
