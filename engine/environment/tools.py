"""Environment-aware tool handlers — stateless functions called by the agent tool registry.

Each handler accepts ``(db: Session, datasource_id: str, ...)`` and returns a plain dict.
Error handling is the caller's responsibility.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from engine.environment.service import EnvironmentService

logger = logging.getLogger("dbfox.environment.tools")

_svc = EnvironmentService()


def environment_get_profile(db: Session, datasource_id: str) -> dict[str, Any]:
    """Return a DataEnvironmentProfile with env/dialect/catalog_status/table_count/warnings."""
    profile = _svc.get_profile(db, datasource_id)
    output = profile.model_dump(mode="json")

    try:
        from engine.environment.database_map import build_database_map, render_map_for_prompt
        db_map = build_database_map(datasource_id, db_session=db)
        if db_map is not None:
            output["database_map"] = db_map.model_dump(mode="json")
            output["database_map_summary"] = render_map_for_prompt(db_map)
    except Exception as exc:
        logger.warning("Failed to build DatabaseMap: %s", exc)

    return output


def schema_list_tables(db: Session, datasource_id: str) -> dict[str, Any]:
    """List all known tables for the current datasource from the system catalog."""
    snapshot = _svc.get_catalog_snapshot(db, datasource_id)

    if not snapshot.tables:
        sync_result = _svc.ensure_catalog(db, datasource_id)
        snapshot = _svc.get_catalog_snapshot(db, datasource_id)
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
    return {"message": msg, "tables": table_list, "table_count": len(table_list)}


def schema_describe_table(db: Session, datasource_id: str, table_name: str) -> dict[str, Any]:
    """Describe a specific table with columns, types, nullability, keys, defaults."""
    table_snapshot = _svc.describe_table(db, datasource_id, table_name)
    if table_snapshot is None:
        raise ValueError(f"Table '{table_name}' not found in catalog.")

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
    return {
        "table_name": table_name,
        "columns": col_list,
        "sample_rows": [],
        "row_count_estimate": table_snapshot.row_count_estimate,
    }


def schema_refresh_catalog(db: Session, datasource_id: str, reason: str = "") -> dict[str, Any]:
    """Re-introspect the live datasource and sync to the DBFox catalog."""
    result = _svc.ensure_catalog(db, datasource_id)
    return {
        "dialect": "resolved",
        "tables_created": result.tables_created,
        "tables_updated": result.tables_updated,
        "tables_removed": result.tables_removed,
        "columns_created": result.columns_created,
        "columns_updated": result.columns_updated,
        "columns_removed": result.columns_removed,
        "synced": result.synced,
        "reason": reason,
    }
