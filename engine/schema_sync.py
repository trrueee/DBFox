"""
.. deprecated::
    This module is superseded by ``engine.environment.schema_catalog_sync``
    which uses an upsert strategy and is the single source of truth for all
    schema sync operations as of 2026-06-20 (MVP simplification).

    Kept for the ``build_er_diagram_data()`` helper and for backward
    compatibility.  New code should call ``ensure_catalog()`` instead.
"""
from __future__ import annotations

import logging
import json
from datetime import UTC, datetime
from typing import Any
from pathlib import Path

from engine.app.errors import public_message

from sqlalchemy.orm import Session

from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.errors import DataSourceConnectionError
from engine.environment.schema_catalog_sync import ensure_catalog

logger = logging.getLogger("dbfox.schema_sync")


def _ai_enrich_warning(enrich_result: dict[str, Any]) -> str | None:
    if enrich_result.get("ai_enriched") is not False:
        return None
    reason = str(enrich_result.get("reason") or "").strip()
    if not reason or reason == "no structural changes":
        return None
    return f"AI 语义打分未完成：{reason}"


def sync_schema(
    db: Session,
    datasource_id: str,
    *,
    ai_enrich: bool = True,
    llm_credential_id: str | None = None,
    ai_api_base: str | None = None,
    ai_model_name: str | None = None,
) -> dict[str, Any]:
    """
    Synchronize metadata into local SQLite without deleting the previous snapshot
    until the new snapshot has been gathered successfully.
    """
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise ValueError("Data source not found")

    if ds.db_type == "sqlite":
        path = Path(str(ds.database_name or "")).expanduser()
        if not path.is_file():
            raise DataSourceConnectionError(
                f"SQLite database file does not exist: {path}"
            )

    try:
        result = ensure_catalog(
            db,
            datasource_id,
            ai_enrich=ai_enrich,
            llm_credential_id=llm_credential_id,
            ai_api_base=ai_api_base,
            ai_model_name=ai_model_name,
        )

        now = datetime.now(UTC)
        db.query(DataSource).filter(DataSource.id == datasource_id).update(
            {
                "last_sync_at": now,
                "last_sync_status": "success",
                "last_sync_error": None,
            }
        )
        db.commit()

        tables_synced = (result.tables_created or 0) + (result.tables_updated or 0)

        response: dict[str, Any] = {
            "ok": True,
            "tablesSynced": tables_synced,
            "message": "Schema synchronized successfully.",
        }

        if ai_enrich:
            configured_credential_id = str(llm_credential_id or "").strip()
            enrich_result = result.ai_enrich_result or {
                "ai_enriched": False,
                "enriched_count": 0,
                "reason": "请先在设置中配置 LLM 凭据。" if not configured_credential_id else "Unknown reason",
            }
            response["aiEnrich"] = enrich_result
            warning = _ai_enrich_warning(enrich_result)
            if warning:
                response["warnings"] = [warning]

        return response

    except Exception as e:
        db.rollback()
        now = datetime.now(UTC)
        db.query(DataSource).filter(DataSource.id == datasource_id).update(
            {
                "last_sync_at": now,
                "last_sync_status": "failed",
                "last_sync_error": public_message(str(e)),
            }
        )
        db.commit()
        raise ValueError(f"Schema sync failed: {public_message(str(e))}")


def _guess_module_tag(table_name: str) -> str | None:
    return None


def _resolve_inferred_target(col_name: str, table_names: set[str]) -> str | None:
    """Try to match a column name like 'user_id' to an existing table like 'users'."""
    if not col_name.endswith("_id"):
        return None
    base = col_name[:-3]
    candidates = [
        base,
        base + "s",
        base + "es",
        base.rstrip("s") if base.endswith("s") else None,
    ]
    for candidate in candidates:
        if candidate and candidate in table_names:
            return candidate
    return None


def build_er_diagram_data(db: Session, datasource_id: str) -> dict[str, Any]:
    """
    Constructs ER diagram node and link data based on synchronized tables & columns in SQLite.

    Returns nodes with module_tag and edges with edge_type ("real" | "inferred").
    Inferred edges are guessed from column names ending in _id that match a known table.
    """
    tables = db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()

    nodes = []
    edges = []

    table_id_to_name = {str(t.id): str(t.table_name) for t in tables}
    table_name_set = {str(t.table_name) for t in tables}

    # Track which (source, target) pairs already have real FK edges to avoid duplicates
    real_fk_pairs: set[tuple[str, str]] = set()

    for t in tables:
        table_name = str(t.table_name)
        fields = []
        fk_source_cols: list[str] = []

        for col in t.columns:
            column_name = str(col.column_name)
            fields.append(
                {
                    "name": column_name,
                    "type": str(col.column_type or ""),
                    "is_pk": bool(col.is_primary_key),
                    "is_fk": bool(col.is_foreign_key),
                    "comment": str(col.column_comment or ""),
                }
            )

            if col.is_foreign_key and col.foreign_table_id:
                target_table_name = table_id_to_name.get(str(col.foreign_table_id))
                target_col = db.query(SchemaColumn).filter(SchemaColumn.id == col.foreign_column_id).first()
                target_col_name = str(target_col.column_name) if target_col else "id"

                if target_table_name:
                    real_fk_pairs.add((table_name, target_table_name))
                    fk_source_cols.append(column_name)
                    edges.append(
                        {
                            "id": f"fk-{table_name}-{column_name}__to__{target_table_name}-{target_col_name}",
                            "source": table_name,
                            "sourceHandle": column_name,
                            "target": target_table_name,
                            "targetHandle": target_col_name,
                            "label": "FK",
                            "edge_type": "real",
                        }
                    )

        # Inferred FK edges: columns ending in _id, not already real FK, matching a known table
        for col in t.columns:
            column_name = str(col.column_name)
            if col.is_foreign_key and col.foreign_table_id:
                continue  # already handled as real FK
            if not column_name.endswith("_id"):
                continue

            target_table_name = _resolve_inferred_target(column_name, table_name_set)
            if not target_table_name or target_table_name == table_name:
                continue
            if (table_name, target_table_name) in real_fk_pairs:
                continue

            target_table = next((x for x in tables if str(x.table_name) == target_table_name), None)
            target_pk_col = "id"
            if target_table:
                # Prefer an actual PK column name
                for tc in target_table.columns:
                    if tc.is_primary_key:
                        target_pk_col = str(tc.column_name)
                        break

            edge_id = f"inf-{table_name}-{column_name}__to__{target_table_name}-{target_pk_col}"
            if any(e["id"] == edge_id for e in edges):
                continue

            edges.append(
                {
                    "id": edge_id,
                    "source": table_name,
                    "sourceHandle": column_name,
                    "target": target_table_name,
                    "targetHandle": target_pk_col,
                    "label": "推断",
                    "edge_type": "inferred",
                }
            )

        nodes.append(
            {
                "id": table_name,
                "label": table_name,
                "comment": t.table_comment or "",
                "module_tag": _guess_module_tag(table_name),
                "fields": fields,
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
    }
