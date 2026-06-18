"""db.preview — safe live data preview from a single table."""

from __future__ import annotations

import time
from typing import Any

from engine.tools.runtime.context import ToolContext
from engine.agent_core.types import ToolObservation
from engine.models import SchemaColumn
from engine.sql.executor import execute_query
from engine.tools.db._common import (
    DEFAULT_PREVIEW_ROWS,
    MAX_PREVIEW_ROWS,
    _catalog_table,
    _clamp,
    _datasource,
    _execution_failed,
    _failed,
    _looks_sensitive,
    _ordered_columns,
    _string_list,
    _success,
    tool_handler,
)


def db_preview(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Preview a small, safe sample of live data from one table.

    Safety: column whitelist, LIMIT ≤ 20, TrustGate, timeout, redaction.
    """
    start = time.perf_counter()
    table_name = str(args.get("table") or args.get("table_name") or "").strip()
    if not table_name:
        return _failed("db.preview", args, "table is required.", start)

    catalog_table = _catalog_table(ctx.db, ctx.request.datasource_id, table_name)
    if catalog_table is None:
        return _failed("db.preview", args, f"Unknown table: {table_name}", start)

    available = {str(c.column_name): c for c in _ordered_columns(catalog_table)}
    requested = _resolve_preview_columns(args, available)
    unknown = [n for n in requested if n not in available]
    if unknown:
        return _failed(
            "db.preview", args,
            f"Unknown column(s) for {table_name}: {', '.join(unknown)}",
            start,
        )

    requested_limit = _clamp(int(args.get("limit", DEFAULT_PREVIEW_ROWS) or DEFAULT_PREVIEW_ROWS), 1, MAX_PREVIEW_ROWS)
    dialect = (ctx.request.datasource_id and _resolve_dialect(ctx)) or "mysql"
    sql = _build_preview_sql(table_name, requested, requested_limit, args, dialect)

    try:
        result = execute_query(
            ctx.db,
            ctx.request.datasource_id,
            sql,
            question=f"Preview table {table_name}",
            safety_policy="table_preview",
            redact=True,
        )
    except Exception as exc:
        return _execution_failed("db.preview", args, exc, start)

    rows = result.get("rows") or []
    safe_sql = str((result.get("safetyDecision") or {}).get("safe_sql") or result.get("safe_sql") or sql)

    output = {
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
    }
    return _success("db.preview", args, output, start)


# ===================================================================
# db.preview helpers
# ===================================================================


def _resolve_dialect(ctx: ToolContext) -> str:
    ds = _datasource(ctx.db, ctx.request.datasource_id)
    return (ds.db_type or "mysql").lower()


def _resolve_preview_columns(args: dict[str, Any], available: dict[str, SchemaColumn]) -> list[str]:
    requested = _string_list(args.get("columns"))
    if not requested:
        # default: first 8 non-sensitive columns
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
# db.query helpers (also shared with db.query module)
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
