from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from typing import Any

from engine.models import DataSource, QueryHistory, SchemaColumn, SchemaTable
from engine.tools.db._common import (
    _column_summary,
    _datasource,
    _catalog_tables,
    _filter_tables,
    _missing_table_names,
    _ordered_columns,
    _string_list,
)

logger = logging.getLogger("dbfox.tools.db.observe")


_RULES_CACHE: dict[str, list[Any]] = {}
_TABLE_NAMES_CACHE: dict[str, str] = {}
_REVERSE_FK_CACHE: dict[str, list[str]] = {}

# Threshold above which db.observe returns a lightweight summary instead of a
# full table listing.  Large enterprise catalogs (200-2000+ tables) must not
# be dumped into the model's context.
_LARGE_CATALOG_THRESHOLD = 30


def db_observe(db: Session, datasource_id: str) -> dict[str, Any]:
    """Return the database map — tables, domains, counts, query stats.

    For catalogs with more than ``_LARGE_CATALOG_THRESHOLD`` tables, returns a
    lightweight summary (dialect, table count, domain breakdown, and navigation
    hints) instead of the full table listing, to avoid blowing up the model
    context.
    """
    _RULES_CACHE.pop(datasource_id, None)
    tables = _catalog_tables(db, datasource_id)
    table_count = len(tables)

    ds = _datasource(db, datasource_id)

    output: dict[str, Any] = {
        "datasource_id": ds.id,
        "datasource_name": ds.name,
        "dialect": ds.db_type or "mysql",
        "catalog_status": ds.last_sync_status or ("ready" if tables else "empty"),
        "last_sync_at": ds.last_sync_at.isoformat() if ds.last_sync_at else None,
        "table_count": table_count,
        "warnings": _catalog_warnings(tables),
    }

    # ── Large catalog: lightweight summary only ──────────────────────────
    if table_count > _LARGE_CATALOG_THRESHOLD:
        output["mode"] = "summary"
        output["domains"] = _domain_sections(db, tables)
        output["schemas"] = _schema_sections(db, tables)

        # Navigation hints guide the agent toward the right exploration tools.
        output["next_action_hint"] = (
            f"This is a large database ({table_count} tables). "
            f"Do NOT try to list all tables. Instead:\n"
            f"1. Use db.search(\"<keywords>\") to find relevant tables by name, "
            f"column, comment, or business term.\n"
            f"2. Use schema.list_tables_page(offset=0, limit=20) to browse "
            f"tables page-by-page if you need an overview.\n"
            f"3. Use schema.expand_related_tables(\"<table>\") to explore "
            f"foreign-key neighbors of a candidate table."
        )
        return output

    # ── Small / medium catalog: full listing ─────────────────────────────
    # Populate memory caches for table names and reverse FKs to optimize queries
    global _TABLE_NAMES_CACHE, _REVERSE_FK_CACHE
    _TABLE_NAMES_CACHE = {str(t.id): str(t.table_name) for t in tables}

    from engine.models import SchemaColumn
    fk_cols = (
        db.query(SchemaColumn)
        .join(SchemaTable, SchemaColumn.table_id == SchemaTable.id)
        .filter(SchemaTable.data_source_id == datasource_id, SchemaColumn.is_foreign_key == True)
        .all()
    )

    rev_fk = defaultdict(list)
    for col in fk_cols:
        if col.foreign_table_id and col.table_id:
            ref_table_name = _TABLE_NAMES_CACHE.get(str(col.table_id))
            if ref_table_name:
                rev_fk[str(col.foreign_table_id)].append(ref_table_name)
    _REVERSE_FK_CACHE = dict(rev_fk)

    output["mode"] = "full"
    output["schemas"] = _schema_sections(db, tables)
    output["domains"] = _domain_sections(db, tables)

    return output


def _catalog_warnings(tables: list[SchemaTable]) -> list[str]:
    warnings = []
    if not tables:
        warnings.append("No tables found in catalog. Run schema_refresh_catalog to inspect.")
    return warnings


def _schema_sections(db: Session, tables: list[SchemaTable]) -> list[dict[str, Any]]:
    grouped: dict[str, list[SchemaTable]] = defaultdict(list)
    for t in tables:
        grouped[str(t.table_schema or "default")].append(t)
    return [
        {
            "name": schema,
            "table_count": len(rows),
            "tables": [_schema_table_summary(db, t) for t in sorted(rows, key=lambda x: str(x.table_name))],
        }
        for schema, rows in sorted(grouped.items())
    ]


def _schema_table_summary(db: Session, table: SchemaTable) -> dict[str, Any]:
    return {
        "name": str(table.table_name),
        "schema": str(table.table_schema or ""),
        "type": str(table.table_type or "table"),
        "comment": str(table.table_comment or ""),
        "columns": len(table.columns or []),
        "row_estimate": table.row_count_estimate or 0,
        "primary_key": [str(c.column_name) for c in _ordered_columns(table) if c.is_primary_key],
        "tags": _table_tags(db, table),
        "connected_tables": sorted(_connected_table_names(db, table)),
    }


# First definition of _query_stats_for_table removed to prevent duplicates


def _domain_sections(db: Session, tables: list[SchemaTable]) -> list[dict[str, Any]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for t in tables:
        tags = _table_tags(db, t)
        domain = tags[0] if tags else "other"
        groups[domain].append(str(t.table_name))
    return [
        {"name": d, "label": d, "tables": sorted(names), "table_count": len(names)}
        for d, names in sorted(groups.items())
    ]


def _table_tags(db: Session, table: SchemaTable) -> list[str]:
    from engine.models import DomainTagRule
    name = str(table.table_name or "").lower()
    ds_id = table.data_source_id
    
    if ds_id not in _RULES_CACHE:
        _RULES_CACHE[ds_id] = (
            db.query(DomainTagRule)
            .filter(DomainTagRule.data_source_id == ds_id)
            .order_by(DomainTagRule.priority.desc())
            .all()
        )
    rules = _RULES_CACHE[ds_id]
    
    tags: list[str] = []
    for rule in rules:
        if rule.pattern and rule.pattern.lower() in name and rule.tag not in tags:
            tags.append(rule.tag)
    return tags or ["other"]


def _connected_table_names(db: Session, table: SchemaTable) -> set[str]:
    connected: set[str] = set()
    for col in (table.columns or []):
        if col.is_foreign_key and col.foreign_table_id:
            target_name = _TABLE_NAMES_CACHE.get(str(col.foreign_table_id))
            if target_name:
                connected.add(target_name)
            else:
                target = db.query(SchemaTable).filter(SchemaTable.id == col.foreign_table_id).first()
                if target is not None:
                    connected.add(str(target.table_name))
    reverse_list = _REVERSE_FK_CACHE.get(str(table.id))
    if reverse_list is not None:
        connected.update(reverse_list)
    else:
        reverse = (
            db.query(SchemaColumn)
            .filter(SchemaColumn.foreign_table_id == table.id)
            .all()
        )
        for col in reverse:
            if col.table is not None:
                connected.add(str(col.table.table_name))
    return connected


# ── Re-exports kept for db_tools.py compatibility ──────────────────────────

def _fk_summary(col: SchemaColumn) -> dict[str, Any]:
    return {
        "column": str(col.column_name),
        "references_table": str(col.foreign_table.table_name) if col.foreign_table else None,
        "references_column": str(col.foreign_column.column_name) if col.foreign_column else None,
    }


def _query_stats_for_table(db: Session, datasource_id: str, table_name: str) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=90)
    records = (
        db.query(QueryHistory.created_at)
        .filter(
            QueryHistory.data_source_id == datasource_id,
            QueryHistory.created_at >= since,
            QueryHistory.executed_sql.like(f"%{table_name}%")
        )
        .all()
    )
    hits = [r.created_at for r in records]
    return {"hit_count": len(hits), "last_queried_at": max(hits).isoformat() if hits else None}


def _table_card(db: Session, datasource_id: str, table: SchemaTable) -> dict[str, Any]:
    columns = _ordered_columns(table)
    pk = [str(c.column_name) for c in columns if c.is_primary_key]
    stats = _query_stats_for_table(db, datasource_id, str(table.table_name))
    return {
        "name": str(table.table_name), "schema": str(table.table_schema or ""),
        "type": str(table.table_type or "table"), "comment": str(table.table_comment or ""),
        "row_estimate": table.row_count_estimate or 0,
        "columns": [_column_summary(c) for c in columns],
        "primary_key": pk[0] if len(pk) == 1 else pk,
        "foreign_keys": [_fk_summary(c) for c in columns if c.is_foreign_key],
        "connected_tables": sorted(_connected_table_names(db, table)),
        "tags": _table_tags(db, table),
        "query_hit_count": stats["hit_count"], "last_queried_at": stats["last_queried_at"],
    }


def _validate_mode(mode: Any) -> str:
    if mode in ("schema", "tables"):
        return str(mode)
    return "overview"
