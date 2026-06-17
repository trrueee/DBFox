from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from engine.agent_core.tool_registry import ToolContext
from engine.models import DataSource, QueryHistory, SchemaColumn, SchemaTable
from engine.tools.db._common import (
    _column_summary,
    _datasource,
    _catalog_tables,
    _filter_tables,
    _missing_table_names,
    _ordered_columns,
    _string_list,
    tool_handler,
)

logger = logging.getLogger("dbfox.tools.db.observe")


@tool_handler("db.observe")
def db_observe(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Return the database map — tables, domains, counts, query stats."""
    mode = _validate_mode(args.get("mode"))
    table_names = _string_list(args.get("table_names"))

    tables = _catalog_tables(ctx.db, ctx.request.datasource_id)
    ds = _datasource(ctx.db, ctx.request.datasource_id)
    selected = _filter_tables(tables, table_names)

    output: dict[str, Any] = {
        "datasource_id": ds.id,
        "datasource_name": ds.name,
        "dialect": ds.db_type or "mysql",
        "mode": mode,
        "catalog_status": ds.last_sync_status or ("ready" if tables else "empty"),
        "last_sync_at": ds.last_sync_at.isoformat() if ds.last_sync_at else None,
        "table_count": len(tables),
        "warnings": _catalog_warnings(tables),
    }

    if mode in ("overview", "schema"):
        output["schemas"] = _schema_sections(ctx.db, selected or tables)
        output["domains"] = _domain_sections(ctx.db, selected or tables)
    elif mode == "tables":
        output["tables"] = [_table_card(ctx.db, ds.id, table) for table in selected]
        output["missing_tables"] = _missing_table_names(tables, table_names)

    return output


def _validate_mode(mode: Any) -> str:
    if mode in ("schema", "tables"):
        return str(mode)
    return "overview"


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


def _table_card(db: Session, datasource_id: str, table: SchemaTable) -> dict[str, Any]:
    columns = _ordered_columns(table)
    pk = [str(c.column_name) for c in columns if c.is_primary_key]
    stats = _query_stats_for_table(db, datasource_id, str(table.table_name))
    return {
        "name": str(table.table_name),
        "schema": str(table.table_schema or ""),
        "type": str(table.table_type or "table"),
        "comment": str(table.table_comment or ""),
        "row_estimate": table.row_count_estimate or 0,
        "columns": [_column_summary(c) for c in columns],
        "primary_key": pk[0] if len(pk) == 1 else pk,
        "foreign_keys": [_fk_summary(c) for c in columns if c.is_foreign_key],
        "connected_tables": sorted(_connected_table_names(db, table)),
        "tags": _table_tags(db, table),
        "query_hit_count": stats["hit_count"],
        "last_queried_at": stats["last_queried_at"],
    }


def _query_stats_for_table(db: Session, datasource_id: str, table_name: str) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=90)
    records = (
        db.query(QueryHistory.executed_sql, QueryHistory.created_at)
        .filter(
            QueryHistory.data_source_id == datasource_id,
            QueryHistory.created_at >= since,
        )
        .all()
    )
    hits = [r.created_at for r in records if r.executed_sql and table_name in r.executed_sql]
    return {
        "hit_count": len(hits),
        "last_queried_at": max(hits).isoformat() if hits else None,
    }


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
    """Derive domain tags from table name.

    Reads database-configured domain tag rules, with automatic bootstrapping
    if no rules exist for the datasource.
    """
    from engine.models import DomainTagRule
    name = str(table.table_name or "").lower()
    
    rules = (
        db.query(DomainTagRule)
        .filter(DomainTagRule.data_source_id == table.data_source_id)
        .order_by(DomainTagRule.priority.desc())
        .all()
    )
    
    if not rules:
        default_patterns = [
            ("user", ["user", "member", "customer", "account"]),
            ("order", ["order", "cart", "coupon"]),
            ("product", ["product", "category", "sku", "inventory", "item"]),
            ("payment", ["payment", "pay", "refund", "transaction"]),
            ("shipping", ["shipping", "address", "carrier", "logistics"]),
            ("analytics", ["analytics", "click", "recommendation", "event", "log"]),
            ("system", ["system", "admin", "setting", "config"]),
            ("content", ["article", "post", "comment", "review", "tag"]),
        ]
        for tag, needles in default_patterns:
            for needle in needles:
                db.add(
                    DomainTagRule(
                        data_source_id=table.data_source_id,
                        pattern=needle,
                        tag=tag,
                        priority=10,
                    )
                )
        try:
            db.commit()
        except Exception:
            db.rollback()
            
        rules = (
            db.query(DomainTagRule)
            .filter(DomainTagRule.data_source_id == table.data_source_id)
            .order_by(DomainTagRule.priority.desc())
            .all()
        )
        
    tags: list[str] = []
    for rule in rules:
        if rule.pattern in name:
            if rule.tag not in tags:
                tags.append(rule.tag)
                
    return tags or ["other"]


def _connected_table_names(db: Session, table: SchemaTable) -> set[str]:
    connected: set[str] = set()
    for col in (table.columns or []):
        if col.is_foreign_key and col.foreign_table_id:
            target = db.query(SchemaTable).filter(SchemaTable.id == col.foreign_table_id).first()
            if target is not None:
                connected.add(str(target.table_name))
    reverse = (
        db.query(SchemaColumn)
        .filter(SchemaColumn.foreign_table_id == table.id)
        .all()
    )
    for col in reverse:
        if col.table is not None:
            connected.add(str(col.table.table_name))
    return connected


def _fk_summary(col: SchemaColumn) -> dict[str, Any]:
    fk_table = getattr(col, "foreign_table", None)
    fk_col = getattr(col, "foreign_column", None)
    return {
        "column": str(col.column_name),
        "references_table": str(fk_table.table_name) if fk_table else None,
        "references_column": str(fk_col.column_name) if fk_col else None,
    }
