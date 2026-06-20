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


def schema_list_tables_page(
    db: Session,
    datasource_id: str,
    offset: int = 0,
    limit: int = 20,
    name_filter: str | None = None,
) -> dict[str, Any]:
    """Paginated table listing for large catalogs.

    Reuses ``EnvironmentService.get_catalog_snapshot()`` so the output shape is
    consistent with ``schema.list_tables``.  Returns a page of tables plus
    pagination metadata.
    """
    snapshot = _svc.get_catalog_snapshot(db, datasource_id)
    tables = snapshot.tables

    # ---- filtering ----------------------------------------------------------
    if name_filter:
        nf = name_filter.strip().lower()
        tables = [t for t in tables if nf in t.table_name.lower()]

    total = len(tables)

    # ---- pagination ---------------------------------------------------------
    page = tables[offset : offset + limit]
    has_more = (offset + limit) < total

    return {
        "tables": [
            {
                "table_name": t.table_name,
                "columns_count": t.column_count,
                "row_count_estimate": t.row_count_estimate,
                "table_type": t.table_type,
                "comment": t.comment,
            }
            for t in page
        ],
        "page": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "returned": len(page),
            "has_more": has_more,
        },
        "catalog_status": snapshot.catalog_status,
    }


def schema_expand_related_tables(
    db: Session,
    datasource_id: str,
    table_name: str,
    depth: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """Expand from a seed table to its FK neighbours (depth=1).

    Reuses the foreign-key relationships already computed by
    ``EnvironmentService.get_catalog_snapshot()``, then walks outward one hop
    from the seed table.
    """
    snapshot = _svc.get_catalog_snapshot(db, datasource_id)
    relationships = snapshot.relationships or []
    table_map = {t.table_name: t for t in snapshot.tables}

    if table_name not in table_map:
        raise ValueError(f"Table '{table_name}' not found in catalog.")

    # ---- collect 1-hop neighbours -------------------------------------------
    neighbours: dict[str, dict[str, Any]] = {}  # table_name → rel info
    for rel in relationships:
        if rel.source_table == table_name:
            target = rel.referenced_table
            if target not in neighbours:
                neighbours[target] = {
                    "table_name": target,
                    "relationship": "outgoing_fk",
                    "via_column": rel.column_name,
                    "referenced_column": rel.referenced_column,
                }
        elif rel.referenced_table == table_name:
            source = rel.source_table
            if source not in neighbours:
                neighbours[source] = {
                    "table_name": source,
                    "relationship": "incoming_fk",
                    "via_column": rel.column_name,
                    "referenced_column": rel.referenced_column,
                }

    # Enrich with column_count / row_estimate from the snapshot
    neighbour_list: list[dict[str, Any]] = []
    for name, info in list(neighbours.items())[:limit]:
        t_snap = table_map.get(name)
        info["columns_count"] = t_snap.column_count if t_snap else 0
        info["row_count_estimate"] = t_snap.row_count_estimate if t_snap else None
        info["table_type"] = t_snap.table_type if t_snap else "table"
        info["comment"] = t_snap.comment if t_snap else None
        neighbour_list.append(info)

    seed_snap = table_map[table_name]
    return {
        "seed_table": {
            "table_name": seed_snap.table_name,
            "columns_count": seed_snap.column_count,
            "row_count_estimate": seed_snap.row_count_estimate,
            "table_type": seed_snap.table_type,
        },
        "related_tables": neighbour_list,
        "total_related": len(neighbours),
        "returned": len(neighbour_list),
        "depth": depth,
        "limit": limit,
        "has_more": len(neighbours) > limit,
    }
