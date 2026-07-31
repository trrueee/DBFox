from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from engine.models import DomainTagRule, SchemaColumn, SchemaTable
from engine.tools.db._common import (
    _datasource,
    _ordered_columns,
)

logger = logging.getLogger("dbfox.tools.db_observe")


@dataclass(frozen=True, slots=True)
class _DomainRule:
    pattern: str
    tag: str


@dataclass(frozen=True, slots=True)
class _ObservationContext:
    """Immutable catalog data scoped to one ``db_observe`` invocation."""

    table_names: Mapping[str, str]
    reverse_foreign_keys: Mapping[str, tuple[str, ...]]
    domain_rules: tuple[_DomainRule, ...]

# Threshold above which db_observe returns a lightweight summary instead of a
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
    ds = _datasource(db, datasource_id)
    table_count = (
        db.query(func.count(SchemaTable.id))
        .filter(SchemaTable.data_source_id == datasource_id)
        .scalar()
        or 0
    )

    output: dict[str, Any] = {
        "datasource_id": ds.id,
        "datasource_name": ds.name,
        "dialect": ds.db_type or "mysql",
        "catalog_status": ds.last_sync_status or ("ready" if table_count else "empty"),
        "last_sync_at": ds.last_sync_at.isoformat() if ds.last_sync_at else None,
        "table_count": table_count,
        "warnings": _catalog_warnings(table_count),
    }

    # ── Large catalog: lightweight summary only ──────────────────────────
    if table_count > _LARGE_CATALOG_THRESHOLD:
        tables = (
            db.query(
                SchemaTable.table_schema,
                SchemaTable.table_name,
            )
            .filter(SchemaTable.data_source_id == datasource_id)
            .order_by(SchemaTable.table_schema, SchemaTable.table_name)
            .all()
        )
        output["mode"] = "summary"
        domain_rules = _load_domain_rules(db, datasource_id)
        output["domains"] = _domain_summaries(domain_rules, tables)
        output["schemas"] = _schema_summaries(tables)

        # Navigation hints guide the agent toward the right exploration tools.
        output["next_action_hint"] = (
            f"This is a large database ({table_count} tables). "
            f"Do NOT try to list all tables. Instead:\n"
            f"1. Use schema_search with one to four focused queries to find relevant tables, "
            f"column, comment, or business term.\n"
            f"2. Use schema_list with a cursor and limit to browse "
            f"tables page-by-page if you need an overview.\n"
            f"3. Use schema_inspect on exact tables to inspect columns and relationships "
            f"foreign-key neighbors of a candidate table."
        )
        return output

    # ── Small / medium catalog: full listing ─────────────────────────────
    tables = (
        db.query(SchemaTable)
        .options(selectinload(SchemaTable.columns))
        .filter(SchemaTable.data_source_id == datasource_id)
        .order_by(SchemaTable.table_schema, SchemaTable.table_name)
        .all()
    )
    context = _build_observation_context(db, datasource_id, tables)
    output["mode"] = "full"
    output["schemas"] = _schema_sections(context, tables)
    output["domains"] = _domain_sections(context, tables)

    return output


def _build_observation_context(
    db: Session,
    datasource_id: str,
    tables: list[SchemaTable],
) -> _ObservationContext:
    table_names = {
        str(table.id): str(table.table_name)
        for table in tables
    }
    reverse_foreign_keys: dict[str, list[str]] = defaultdict(list)
    foreign_keys = (
        db.query(SchemaColumn.table_id, SchemaColumn.foreign_table_id)
        .join(SchemaTable, SchemaColumn.table_id == SchemaTable.id)
        .filter(
            SchemaTable.data_source_id == datasource_id,
            SchemaColumn.is_foreign_key.is_(True),
            SchemaColumn.foreign_table_id.is_not(None),
        )
        .all()
    )
    for source_table_id, target_table_id in foreign_keys:
        source_name = table_names.get(str(source_table_id))
        if source_name:
            reverse_foreign_keys[str(target_table_id)].append(source_name)

    domain_rules = _load_domain_rules(db, datasource_id)
    return _ObservationContext(
        table_names=MappingProxyType(table_names),
        reverse_foreign_keys=MappingProxyType({
            table_id: tuple(sorted(set(source_names)))
            for table_id, source_names in reverse_foreign_keys.items()
        }),
        domain_rules=domain_rules,
    )


def _load_domain_rules(
    db: Session,
    datasource_id: str,
) -> tuple[_DomainRule, ...]:
    rules = (
        db.query(DomainTagRule.pattern, DomainTagRule.tag)
        .filter(DomainTagRule.data_source_id == datasource_id)
        .order_by(DomainTagRule.priority.desc())
        .all()
    )
    return tuple(
        _DomainRule(pattern=str(pattern).lower(), tag=str(tag))
        for pattern, tag in rules
        if pattern and tag
    )


def _catalog_warnings(table_count: int) -> list[str]:
    warnings = []
    if table_count == 0:
        warnings.append("No tables found in the catalog. Refresh the datasource catalog before analysis.")
    return warnings


def _schema_summaries(tables: list[Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for table in tables:
        grouped[str(table.table_schema or "default")].append(str(table.table_name))
    return [
        {
            "name": schema,
            "table_count": len(names),
            "sample_tables": sorted(names)[:5],
        }
        for schema, names in sorted(grouped.items())
    ]


def _domain_summaries(
    rules: tuple[_DomainRule, ...],
    tables: list[Any],
) -> list[dict[str, Any]]:
    context = _ObservationContext(
        table_names=MappingProxyType({}),
        reverse_foreign_keys=MappingProxyType({}),
        domain_rules=rules,
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for table in tables:
        grouped[_table_tags(context, table)[0]].append(str(table.table_name))
    return [
        {
            "name": domain,
            "label": domain,
            "table_count": len(names),
            "sample_tables": sorted(names)[:5],
        }
        for domain, names in sorted(grouped.items())
    ]


def _schema_sections(
    context: _ObservationContext,
    tables: list[SchemaTable],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[SchemaTable]] = defaultdict(list)
    for t in tables:
        grouped[str(t.table_schema or "default")].append(t)
    return [
        {
            "name": schema,
            "table_count": len(rows),
            "tables": [
                _schema_table_summary(context, table)
                for table in sorted(rows, key=lambda value: str(value.table_name))
            ],
        }
        for schema, rows in sorted(grouped.items())
    ]


def _schema_table_summary(
    context: _ObservationContext,
    table: SchemaTable,
) -> dict[str, Any]:
    return {
        "name": str(table.table_name),
        "schema": str(table.table_schema or ""),
        "type": str(table.table_type or "table"),
        "comment": str(table.table_comment or ""),
        "columns": len(table.columns or []),
        "row_estimate": table.row_count_estimate or 0,
        "primary_key": [str(c.column_name) for c in _ordered_columns(table) if c.is_primary_key],
        "tags": _table_tags(context, table),
        "connected_tables": sorted(_connected_table_names(context, table)),
    }


def _domain_sections(
    context: _ObservationContext,
    tables: list[SchemaTable],
) -> list[dict[str, Any]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for t in tables:
        tags = _table_tags(context, t)
        domain = tags[0] if tags else "other"
        groups[domain].append(str(t.table_name))
    return [
        {"name": d, "label": d, "tables": sorted(names), "table_count": len(names)}
        for d, names in sorted(groups.items())
    ]


def _table_tags(
    context: _ObservationContext,
    table: Any,
) -> list[str]:
    name = str(table.table_name or "").lower()
    tags: list[str] = []
    for rule in context.domain_rules:
        if rule.pattern in name and rule.tag not in tags:
            tags.append(rule.tag)
    return tags or ["other"]


def _connected_table_names(
    context: _ObservationContext,
    table: SchemaTable,
) -> set[str]:
    connected: set[str] = set()
    for col in (table.columns or []):
        if col.is_foreign_key and col.foreign_table_id:
            target_name = context.table_names.get(str(col.foreign_table_id))
            if target_name:
                connected.add(target_name)
    connected.update(context.reverse_foreign_keys.get(str(table.id), ()))
    return connected
