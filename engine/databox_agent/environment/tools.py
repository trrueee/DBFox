"""Environment-aware tools registered into the agent tool registry.

These tools give the agent the ability to discover, refresh, and
understand the database environment it operates in.
"""
from __future__ import annotations

from typing import Any

from engine.agent.types import ToolObservation
from engine.agent.tool_registry import ToolContext
from engine.models import SchemaTable, SchemaColumn
from engine.databox_agent.environment.schema_catalog_sync import ensure_catalog
from engine.databox_agent.environment.schema_introspector import introspect_datasource


# ---------------------------------------------------------------------------
# schema.list_tables
# ---------------------------------------------------------------------------

def schema_list_tables(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """List all known tables for the current datasource from the system catalog."""
    datasource_id = _datasource_id(ctx)
    tables = (
        ctx.db.query(SchemaTable)
        .filter(SchemaTable.data_source_id == datasource_id)
        .order_by(SchemaTable.table_name)
        .all()
    )

    if not tables:
        sync_result = ensure_catalog(ctx.db, datasource_id)
        tables = (
            ctx.db.query(SchemaTable)
            .filter(SchemaTable.data_source_id == datasource_id)
            .order_by(SchemaTable.table_name)
            .all()
        )
        msg = f"Catalog was empty. Auto-refreshed: {sync_result.tables_created} tables found."
    else:
        msg = f"Found {len(tables)} table(s)."

    table_list = [
        {
            "table_name": t.table_name,
            "columns_count": ctx.db.query(SchemaColumn)
            .filter(SchemaColumn.table_id == t.id).count(),
            "row_count_estimate": t.row_count_estimate,
            "table_type": t.table_type or "table",
        }
        for t in tables
    ]

    return ToolObservation(
        name="list_tables",
        status="success",
        input=args,
        output={"message": msg, "tables": table_list, "table_count": len(table_list)},
        latency_ms=0,
    )


# ---------------------------------------------------------------------------
# schema.describe_table
# ---------------------------------------------------------------------------

def schema_describe_table(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Describe a specific table with columns, types, and sample data."""
    datasource_id = _datasource_id(ctx)
    table_name = str(args.get("table_name") or "")

    table = (
        ctx.db.query(SchemaTable)
        .filter(
            SchemaTable.data_source_id == datasource_id,
            SchemaTable.table_name == table_name,
        )
        .first()
    )

    if table is None:
        return ToolObservation(
            name="describe_table",
            status="failed",
            input=args,
            error=f"Table '{table_name}' not found in catalog.",
            latency_ms=0,
        )

    columns = (
        ctx.db.query(SchemaColumn)
        .filter(SchemaColumn.table_id == table.id)
        .order_by(SchemaColumn.column_name)
        .all()
    )

    col_list = [
        {
            "column_name": c.column_name,
            "data_type": c.data_type,
            "is_nullable": c.is_nullable,
            "is_primary_key": c.is_primary_key,
            "is_foreign_key": c.is_foreign_key,
            "column_default": c.column_default,
        }
        for c in columns
    ]

    inventory = introspect_datasource(ctx.db, datasource_id)
    sample_rows = next(
        (t.sample_rows for t in inventory.tables if t.table_name == table_name),
        [],
    )

    return ToolObservation(
        name="describe_table",
        status="success",
        input=args,
        output={
            "table_name": table_name,
            "columns": col_list,
            "sample_rows": sample_rows,
            "row_count_estimate": table.row_count_estimate,
        },
        latency_ms=0,
    )


# ---------------------------------------------------------------------------
# schema.refresh_catalog
# ---------------------------------------------------------------------------

def schema_refresh_catalog(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Re-introspect the live datasource and sync to the DataBox catalog."""
    datasource_id = _datasource_id(ctx)
    reason = str(args.get("reason") or "")

    try:
        result = ensure_catalog(ctx.db, datasource_id)
        return ToolObservation(
            name="refresh_catalog",
            status="success",
            input=args,
            output={
                "dialect": "resolved",
                "tables_created": result.tables_created,
                "tables_updated": result.tables_updated,
                "tables_removed": result.tables_removed,
                "columns_created": result.columns_created,
                "columns_updated": result.columns_updated,
                "columns_removed": result.columns_removed,
                "synced": result.synced,
                "reason": reason,
            },
            latency_ms=0,
        )
    except Exception as exc:
        return ToolObservation(
            name="refresh_catalog",
            status="failed",
            input=args,
            error=str(exc),
            latency_ms=0,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _datasource_id(ctx: ToolContext) -> str:
    return str(ctx.state.get("datasource_id") or "")
