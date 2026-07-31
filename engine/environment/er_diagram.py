"""Build the ER-diagram read model from the synchronized schema catalog."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy.orm import Session, selectinload

from engine.models import SchemaColumn, SchemaTable


def _inferred_table_name(column_name: str, table_names: set[str]) -> str | None:
    if not column_name.endswith("_id"):
        return None
    base = column_name[:-3]
    candidates = (
        base,
        f"{base}s",
        f"{base}es",
        base[:-1] if base.endswith("s") else None,
    )
    return next(
        (candidate for candidate in candidates if candidate in table_names),
        None,
    )


def build_er_diagram(db: Session, datasource_id: str) -> dict[str, Any]:
    """Return ER nodes and edges without issuing per-column lookup queries."""

    tables = (
        db.query(SchemaTable)
        .options(selectinload(SchemaTable.columns))
        .filter(SchemaTable.data_source_id == datasource_id)
        .order_by(SchemaTable.table_schema, SchemaTable.table_name)
        .all()
    )
    name_counts = Counter(str(table.table_name) for table in tables)

    def table_key(table: SchemaTable) -> str:
        name = str(table.table_name)
        schema = str(table.table_schema or "")
        return f"{schema}.{name}" if schema and name_counts[name] > 1 else name

    table_by_id = {str(table.id): table for table in tables}
    table_key_by_id = {
        table_id: table_key(table)
        for table_id, table in table_by_id.items()
    }
    unique_table_by_name = {
        str(table.table_name): table
        for table in tables
        if name_counts[str(table.table_name)] == 1
    }
    unique_table_names = set(unique_table_by_name)
    column_name_by_id = {
        str(column.id): str(column.column_name)
        for table in tables
        for column in table.columns
    }

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    edge_ids: set[str] = set()
    real_pairs: set[tuple[str, str]] = set()

    for table in tables:
        source = table_key(table)
        fields = [
            {
                "name": str(column.column_name),
                "type": str(column.column_type or ""),
                "is_pk": bool(column.is_primary_key),
                "is_fk": bool(column.is_foreign_key),
                "comment": str(column.column_comment or ""),
            }
            for column in table.columns
        ]

        for column in table.columns:
            if not column.is_foreign_key or not column.foreign_table_id:
                continue
            target = table_key_by_id.get(str(column.foreign_table_id))
            if target is None:
                continue
            column_name = str(column.column_name)
            target_column = column_name_by_id.get(
                str(column.foreign_column_id),
                "id",
            )
            edge_id = f"fk-{source}-{column_name}__to__{target}-{target_column}"
            real_pairs.add((source, target))
            edge_ids.add(edge_id)
            edges.append(
                {
                    "id": edge_id,
                    "source": source,
                    "sourceHandle": column_name,
                    "target": target,
                    "targetHandle": target_column,
                    "label": "FK",
                    "edge_type": "real",
                }
            )

        for column in table.columns:
            column_name = str(column.column_name)
            if column.is_foreign_key and column.foreign_table_id:
                continue
            target_name = _inferred_table_name(
                column_name,
                unique_table_names,
            )
            target_table = unique_table_by_name.get(target_name or "")
            if target_table is None:
                continue
            target = table_key(target_table)
            if target == source or (source, target) in real_pairs:
                continue
            target_column = next(
                (
                    str(candidate.column_name)
                    for candidate in target_table.columns
                    if candidate.is_primary_key
                ),
                "id",
            )
            edge_id = f"inf-{source}-{column_name}__to__{target}-{target_column}"
            if edge_id in edge_ids:
                continue
            edge_ids.add(edge_id)
            edges.append(
                {
                    "id": edge_id,
                    "source": source,
                    "sourceHandle": column_name,
                    "target": target,
                    "targetHandle": target_column,
                    "label": "推断",
                    "edge_type": "inferred",
                }
            )

        nodes.append(
            {
                "id": source,
                "label": source,
                "comment": str(table.table_comment or ""),
                "fields": fields,
            }
        )

    return {"nodes": nodes, "edges": edges}
