"""AI schema enrichment — called from schema.refresh_catalog with ai_enrich=True."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session as OrmSession

from engine.ai_index import (
    build_column_search_text,
    build_table_search_text,
    compute_schema_hash,
    enrich_tables_batch,
)
from engine.models import SchemaColumn, SchemaSearchDoc, SchemaTable

logger = logging.getLogger("databox.ai_enrich")

AI_LLM_TABLE_BATCH = 50
AI_LLM_BATCH_INTERVAL_MS = 200


def ai_enrich_catalog(
    db: OrmSession,
    datasource_id: str,
    *,
    table_batch: int = AI_LLM_TABLE_BATCH,
) -> dict[str, Any]:
    """Run AI enrichment on all changed tables for a datasource."""
    tables = (
        db.query(SchemaTable)
        .filter(SchemaTable.data_source_id == datasource_id)
        .order_by(SchemaTable.table_schema, SchemaTable.table_name)
        .all()
    )

    # 1. Incremental detection via schema_hash
    changed: list[SchemaTable] = []
    for t in tables:
        current_hash = compute_schema_hash(t)
        if current_hash != t.schema_hash:
            changed.append(t)

    if not changed:
        return {"ai_enriched": False, "enriched_count": 0, "reason": "no structural changes"}

    # 2. Batch LLM enrichment
    enriched_count = 0
    for i in range(0, len(changed), table_batch):
        batch = changed[i : i + table_batch]
        context = _build_table_context(db, batch)

        try:
            ai_result = enrich_tables_batch(context)
        except Exception as exc:
            logger.exception("AI enrich batch %d failed: %s", i // table_batch, exc)
            continue

        _write_ai_metadata(db, batch, ai_result)
        _rebuild_search_docs(db, datasource_id, batch, ai_result)
        _update_schema_hashes(batch)

        enriched_count += len(batch)
        if i + table_batch < len(changed):
            time.sleep(AI_LLM_BATCH_INTERVAL_MS / 1000)

    # 3. Cleanup orphan search docs
    _clean_orphan_search_docs(db, datasource_id)

    db.commit()
    return {"ai_enriched": True, "enriched_count": enriched_count, "reason": ""}


def _build_table_context(db: OrmSession, tables: list[SchemaTable]) -> list[dict[str, Any]]:
    """Build LLM input context for a batch of tables."""
    result: list[dict[str, Any]] = []
    for table in tables:
        columns = sorted(
            list(table.columns or []),
            key=lambda c: (c.ordinal_position or 0, str(c.column_name)),
        )
        result.append({
            "name": str(table.table_name),
            "comment": str(table.table_comment or ""),
            "columns": [
                {
                    "name": str(c.column_name),
                    "type": str(c.column_type or c.data_type or ""),
                    "comment": str(c.column_comment or ""),
                    "is_pk": bool(c.is_primary_key),
                    "is_fk": bool(c.is_foreign_key),
                }
                for c in columns
            ],
            "related_tables": sorted(_connected_table_names(db, table)),
        })
    return result


def _write_ai_metadata(db: OrmSession, tables: list[SchemaTable], ai_result: dict[str, Any]) -> None:
    """Write AI-generated metadata back to SchemaTable and SchemaColumn."""
    now = datetime.now(timezone.utc)
    ai_tables = {t["name"]: t for t in ai_result.get("tables", []) if isinstance(t, dict)}

    for table in tables:
        ai = ai_tables.get(str(table.table_name))
        if not ai:
            continue

        table.ai_description = str(ai.get("ai_description") or "") or None
        table.semantic_tags = json.dumps(ai.get("semantic_tags") or [], ensure_ascii=False)
        table.business_terms = json.dumps(ai.get("business_terms") or [], ensure_ascii=False)
        table.aliases = json.dumps(ai.get("aliases") or [], ensure_ascii=False)
        table.table_role = str(ai.get("table_role") or "") or None
        table.grain = str(ai.get("grain") or "") or None
        table.subject_area = str(ai.get("subject_area") or "") or None
        table.ai_confidence = float(ai.get("ai_confidence", 0))
        table.ai_enriched_at = now

        ai_cols = {c["name"]: c for c in ai.get("columns", []) if isinstance(c, dict)}
        for col in table.columns or []:
            ac = ai_cols.get(str(col.column_name))
            if not ac:
                continue
            col.ai_description = str(ac.get("ai_description") or "") or None
            col.semantic_tags = json.dumps(ac.get("semantic_tags") or [], ensure_ascii=False)
            col.business_terms = json.dumps(ac.get("business_terms") or [], ensure_ascii=False)
            col.aliases = json.dumps(ac.get("aliases") or [], ensure_ascii=False)
            col.column_role = str(ac.get("column_role") or "") or None
            col.metric_type = str(ac.get("metric_type") or "") if ac.get("metric_type") else None
            col.is_pii = False
            col.ai_confidence = float(ac.get("ai_confidence", 0))
            col.ai_enriched_at = now


def _rebuild_search_docs(
    db: OrmSession,
    datasource_id: str,
    tables: list[SchemaTable],
    ai_result: dict[str, Any],
) -> None:
    """Rebuild schema_search_docs rows for a batch of tables."""
    now = datetime.now(timezone.utc)
    ai_tables = {t["name"]: t for t in ai_result.get("tables", []) if isinstance(t, dict)}

    # Delete existing rows for these tables
    table_names = [str(t.table_name) for t in tables]
    if table_names:
        db.query(SchemaSearchDoc).filter(
            SchemaSearchDoc.datasource_id == datasource_id,
            SchemaSearchDoc.table_name.in_(table_names),
        ).delete(synchronize_session=False)

    for table in tables:
        ai = ai_tables.get(str(table.table_name))
        tags = ai.get("semantic_tags") if ai else []
        terms = ai.get("business_terms") if ai else []
        _aliases = ai.get("aliases") if ai else []
        role = ai.get("table_role") if ai else None
        grain = ai.get("grain") if ai else None
        desc = ai.get("ai_description") if ai else None
        confidence = float(ai.get("ai_confidence", 0)) if ai else None
        cols = sorted(list(table.columns or []), key=lambda c: (c.ordinal_position or 0, str(c.column_name)))

        col_names = [str(c.column_name) for c in cols]
        col_descs = {str(c.column_name): c.ai_description for c in cols if c.ai_description}

        relation_text = ", ".join(sorted(_connected_table_names(db, table))) or None

        search_text = build_table_search_text(
            table_name=str(table.table_name),
            ai_description=desc,
            semantic_tags=tags if isinstance(tags, list) else None,
            business_terms=terms if isinstance(terms, list) else None,
            aliases=_aliases if isinstance(_aliases, list) else None,
            table_role=role,
            grain=grain,
            column_names=col_names,
            column_ai_descriptions=col_descs,
            relation_text=relation_text,
        )

        db.add(SchemaSearchDoc(
            datasource_id=datasource_id,
            entity_type="table",
            entity_id=str(table.id),
            table_name=str(table.table_name),
            column_name=None,
            name=str(table.table_name),
            ai_description=desc,
            semantic_tags=json.dumps(tags, ensure_ascii=False) if tags else None,
            business_terms=json.dumps(terms, ensure_ascii=False) if terms else None,
            aliases=json.dumps(_aliases, ensure_ascii=False) if _aliases else None,
            table_role=role,
            grain=grain,
            subject_area=ai.get("subject_area") if ai else None,
            column_summary=", ".join(col_names),
            relation_summary=relation_text,
            search_text=search_text,
            ai_confidence=confidence,
            updated_at=now,
        ))

        # Column-level docs
        ai_cols = {c["name"]: c for c in (ai.get("columns") or []) if isinstance(c, dict)} if ai else {}
        for col in cols:
            ac = ai_cols.get(str(col.column_name))
            if not ac:
                continue
            ctags = ac.get("semantic_tags")
            cterms = ac.get("business_terms")
            caliases = ac.get("aliases")
            crole = ac.get("column_role")
            cmtype = ac.get("metric_type")
            cdesc = ac.get("ai_description")
            cconf = float(ac.get("ai_confidence", 0))

            col_search_text = build_column_search_text(
                column_name=str(col.column_name),
                table_name=str(table.table_name),
                ai_description=cdesc,
                semantic_tags=ctags if isinstance(ctags, list) else None,
                business_terms=cterms if isinstance(cterms, list) else None,
                column_role=crole,
                metric_type=cmtype,
            )

            db.add(SchemaSearchDoc(
                datasource_id=datasource_id,
                entity_type="column",
                entity_id=str(col.id),
                table_name=str(table.table_name),
                column_name=str(col.column_name),
                name=str(col.column_name),
                ai_description=cdesc,
                semantic_tags=json.dumps(ctags, ensure_ascii=False) if ctags else None,
                business_terms=json.dumps(cterms, ensure_ascii=False) if cterms else None,
                aliases=json.dumps(caliases, ensure_ascii=False) if caliases else None,
                column_role=crole,
                metric_type=cmtype,
                column_summary=None,
                relation_summary=None,
                search_text=col_search_text,
                ai_confidence=cconf,
                updated_at=now,
            ))

    db.flush()


def _update_schema_hashes(tables: list[SchemaTable]) -> None:
    """Update schema_hash after successful enrichment."""
    for table in tables:
        table.schema_hash = compute_schema_hash(table)


def _clean_orphan_search_docs(db: OrmSession, datasource_id: str) -> None:
    """Remove search docs for tables that no longer exist in catalog."""
    db.query(SchemaSearchDoc).filter(
        SchemaSearchDoc.datasource_id == datasource_id,
        SchemaSearchDoc.entity_type == "table",
        ~SchemaSearchDoc.table_name.in_(
            db.query(SchemaTable.table_name).filter(
                SchemaTable.data_source_id == datasource_id,
            )
        ),
    ).delete(synchronize_session=False)
    db.query(SchemaSearchDoc).filter(
        SchemaSearchDoc.datasource_id == datasource_id,
        SchemaSearchDoc.entity_type == "column",
        ~SchemaSearchDoc.table_name.in_(
            db.query(SchemaTable.table_name).filter(
                SchemaTable.data_source_id == datasource_id,
            )
        ),
    ).delete(synchronize_session=False)


def _connected_table_names(db: OrmSession, table: SchemaTable) -> set[str]:
    """Get FK-connected table names."""
    connected: set[str] = set()
    for col in table.columns or []:
        if col.is_foreign_key and col.foreign_table_id:
            target = db.query(SchemaTable).filter(SchemaTable.id == col.foreign_table_id).first()
            if target:
                connected.add(str(target.table_name))
    return connected
