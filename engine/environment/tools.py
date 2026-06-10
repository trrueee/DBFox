"""Environment-aware tools registered into the agent tool registry.

These tools give the agent the ability to discover, refresh, and
understand the database environment it operates in.

All tools delegate to EnvironmentService for deterministic fact retrieval.
"""

from __future__ import annotations

import logging
from typing import Any

from engine.agent_contracts.types import ToolObservation
from engine.agent_contracts.tool_registry import ToolContext
from engine.environment.service import EnvironmentService

logger = logging.getLogger("databox.environment.tools")

_svc = EnvironmentService()


# ---------------------------------------------------------------------------
# environment.get_profile
# ---------------------------------------------------------------------------

def environment_get_profile(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Return a DataEnvironmentProfile with env/dialect/catalog_status/table_count/warnings."""
    datasource_id = _datasource_id(ctx)
    try:
        profile = _svc.get_profile(ctx.db, datasource_id)
        return ToolObservation(
            name="get_profile",
            status="success",
            input=args,
            output=profile.model_dump(mode="json"),
            latency_ms=0,
        )
    except Exception as exc:
        return ToolObservation(
            name="get_profile",
            status="failed",
            input=args,
            error=str(exc),
            latency_ms=0,
        )


# ---------------------------------------------------------------------------
# schema.list_tables
# ---------------------------------------------------------------------------

def schema_list_tables(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """List all known tables for the current datasource from the system catalog."""
    datasource_id = _datasource_id(ctx)

    snapshot = _svc.get_catalog_snapshot(ctx.db, datasource_id)

    if not snapshot.tables:
        # Catalog is empty — try refreshing
        sync_result = _svc.ensure_catalog(ctx.db, datasource_id)
        snapshot = _svc.get_catalog_snapshot(ctx.db, datasource_id)
        msg = f"Catalog was empty. Auto-refreshed: {sync_result.tables_created} tables found."
    else:
        msg = f"Found {len(snapshot.tables)} table(s)."

    table_list = [
        {
            "table_name": t.table_name,
            "columns_count": t.column_count,
            "row_count_estimate": t.row_count_estimate,
            "table_type": t.table_type,
        }
        for t in snapshot.tables
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

    table_snapshot = _svc.describe_table(ctx.db, datasource_id, table_name)
    if table_snapshot is None:
        return ToolObservation(
            name="describe_table",
            status="failed",
            input=args,
            error=f"Table '{table_name}' not found in catalog.",
            latency_ms=0,
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
        for c in table_snapshot.columns
    ]

    # Sample rows still come from live introspection (not catalog)
    from engine.environment.schema_introspector import introspect_datasource
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
            "row_count_estimate": table_snapshot.row_count_estimate,
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
        result = _svc.ensure_catalog(ctx.db, datasource_id)
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
