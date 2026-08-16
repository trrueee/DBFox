"""AI schema enrichment used by the datasource catalog refresh service."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session as OrmSession

from engine.ai_index import (
    LLM_ENRICH_FAILED,
    compute_schema_hash,
    enrich_tables_batch,
)
from engine.llm.config import LlmConfig
from engine.json_codec import dumps
from engine.models import DataSource, DomainTagRule, SchemaTable

logger = logging.getLogger("dbfox.ai_enrich")

AI_LLM_TABLE_BATCH = 5
AI_LLM_BATCH_INTERVAL_MS = 300
AI_LLM_MAX_TABLES_PER_RUN = 30
AI_LLM_MAX_COLUMNS_PER_TABLE = 60
AI_LLM_MAX_COMMENT_LENGTH = 200
AI_LLM_MAX_PROMPT_CHARS = 24_000


def ai_enrich_catalog(
    db: OrmSession,
    datasource_id: str,
    *,
    table_batch: int = AI_LLM_TABLE_BATCH,
    llm_config: LlmConfig | None = None,
) -> dict[str, Any]:
    """Run AI enrichment on changed tables for a datasource.

    Transaction contract: structural change detection uses a short read
    transaction which ends before the first LLM call. Every successful batch
    writes metadata, rebuilds SearchDocs and bumps ``catalog_revision`` in its
    own short write transaction after re-checking the expected schema hash and
    connection generation. LLM calls never run inside a DB write transaction.
    """
    tables = (
        db.query(SchemaTable)
        .filter(SchemaTable.data_source_id == datasource_id)
        .order_by(SchemaTable.table_schema, SchemaTable.table_name)
        .all()
    )

    changed_ids: list[str] = []
    expected_hashes: dict[str, str | None] = {}
    datasource = db.get(DataSource, datasource_id)
    expected_generation = (
        int(datasource.connection_generation) if datasource is not None else None
    )
    for t in tables:
        current_hash = compute_schema_hash(t)
        if current_hash != t.schema_hash:
            changed_ids.append(str(t.id))
            # Re-check against the structural hash we saw at detection time,
            # not against the stale persisted schema_hash.
            expected_hashes[str(t.id)] = current_hash

    # End the detection read transaction before any remote LLM call.
    db.rollback()

    if not changed_ids:
        return {"ai_enriched": False, "enriched_count": 0, "reason": "no structural changes"}

    if llm_config is None:
        return {"ai_enriched": False, "enriched_count": 0, "reason": "请先在设置中配置 LLM API Key。"}

    # Cap total tables per run to avoid overwhelming the LLM.
    total_changed = len(changed_ids)
    capped = False
    if total_changed > AI_LLM_MAX_TABLES_PER_RUN:
        changed_ids = changed_ids[:AI_LLM_MAX_TABLES_PER_RUN]
        capped = True
        logger.warning(
            "AI enrich: capping to %d/%d changed tables for datasource %s",
            AI_LLM_MAX_TABLES_PER_RUN, total_changed, datasource_id,
        )

    enriched_count = 0
    skipped_stale = 0
    errors: list[str] = []
    for i in range(0, len(changed_ids), table_batch):
        batch_ids = changed_ids[i : i + table_batch]
        batch = list(
            db.query(SchemaTable)
            .filter(SchemaTable.id.in_(batch_ids))
            .order_by(SchemaTable.table_schema, SchemaTable.table_name)
            .all()
        )
        context = _build_table_context(db, batch)

        # Context overflow guard — if a single batch exceeds the prompt budget,
        # shrink the batch size dynamically.
        context_size = len(dumps(context))
        if context_size > AI_LLM_MAX_PROMPT_CHARS:
            logger.warning(
                "AI enrich: batch context %d chars exceeds limit %d — "
                "shrinking batch from %d tables to 1",
                context_size, AI_LLM_MAX_PROMPT_CHARS, len(batch),
            )
            batch = batch[:1]
            batch_ids = batch_ids[:1]
            context = _build_table_context(db, batch)
            context_size = len(dumps(context))
            if context_size > AI_LLM_MAX_PROMPT_CHARS:
                logger.error(
                    "AI enrich: single table '%s' context %d chars still exceeds limit — skipping",
                    str(batch[0].table_name), context_size,
                )
                db.rollback()
                continue

        # End the context-build read transaction before the LLM call.
        db.rollback()

        try:
            ai_result = enrich_tables_batch(
                context,
                llm_config=llm_config,
            )
        except Exception as exc:
            logger.warning(
                "AI enrich batch %d failed (%s)",
                i // table_batch,
                type(exc).__name__,
            )
            errors.append(LLM_ENRICH_FAILED)
            continue

        try:
            fresh_batch = list(
                db.query(SchemaTable)
                .filter(SchemaTable.id.in_(batch_ids))
                .order_by(SchemaTable.table_schema, SchemaTable.table_name)
                .all()
            )
            fresh_datasource = db.get(DataSource, datasource_id)
            if fresh_datasource is None:
                db.rollback()
                errors.append(LLM_ENRICH_FAILED)
                continue
            current_generation = int(fresh_datasource.connection_generation)
            stale = any(
                compute_schema_hash(table) != expected_hashes.get(str(table.id))
                for table in fresh_batch
            )
            if expected_generation != current_generation or stale:
                logger.warning(
                    "AI enrich: skipping stale batch for datasource %s",
                    datasource_id,
                )
                skipped_stale += len(fresh_batch)
                db.rollback()
                continue
            _write_ai_metadata(db, fresh_batch, ai_result)
            from engine.environment.schema_catalog_sync import (
                bump_catalog_revision,
                rebuild_search_docs,
            )
            rebuild_search_docs(db, datasource_id)
            _update_schema_hashes(fresh_batch)
            bump_catalog_revision(db, datasource_id)
            db.commit()
            enriched_count += len(fresh_batch)
        except Exception as exc:
            logger.warning(
                "AI enrich batch %d failed (%s)",
                i // table_batch,
                type(exc).__name__,
            )
            errors.append(LLM_ENRICH_FAILED)
            db.rollback()
            continue

        if i + table_batch < len(changed_ids):
            time.sleep(AI_LLM_BATCH_INTERVAL_MS / 1000)

    if errors and enriched_count == 0 and not skipped_stale:
        return {
            "ai_enriched": False,
            "enriched_count": 0,
            "reason": "; ".join(errors),
            "errors": errors,
        }
    result: dict[str, Any] = {
        "ai_enriched": enriched_count > 0,
        "enriched_count": enriched_count,
        "skipped_stale": skipped_stale,
        "reason": "; ".join(errors),
        "errors": errors,
    }
    if capped:
        result["capped"] = True
        result["total_changed"] = total_changed
        result["max_tables_per_run"] = AI_LLM_MAX_TABLES_PER_RUN
    return result


def _build_table_context(db: OrmSession, tables: list[SchemaTable]) -> list[dict[str, Any]]:
    """Build LLM input context for a batch of tables.

    Safety caps to prevent context overflow:
    - Max ``AI_LLM_MAX_COLUMNS_PER_TABLE`` columns per table
    - Comments truncated to ``AI_LLM_MAX_COMMENT_LENGTH`` chars
    """
    result: list[dict[str, Any]] = []
    for table in tables:
        all_columns = sorted(
            list(table.columns or []),
            key=lambda c: (c.ordinal_position or 0, str(c.column_name)),
        )
        # Prioritise PK/FK columns, then fill up to the cap
        priority_cols = [c for c in all_columns if c.is_primary_key or c.is_foreign_key]
        other_cols = [c for c in all_columns if not (c.is_primary_key or c.is_foreign_key)]
        selected = priority_cols + other_cols
        if len(selected) > AI_LLM_MAX_COLUMNS_PER_TABLE:
            truncated = len(selected) - AI_LLM_MAX_COLUMNS_PER_TABLE
            selected = selected[:AI_LLM_MAX_COLUMNS_PER_TABLE]
            logger.debug(
                "AI enrich: table %s has %d columns, truncating %d for LLM context",
                str(table.table_name), len(all_columns), truncated,
            )

        def _clip(s: str) -> str:
            s = str(s or "")
            return s if len(s) <= AI_LLM_MAX_COMMENT_LENGTH else s[:AI_LLM_MAX_COMMENT_LENGTH - 3] + "..."

        result.append({
            "name": str(table.table_name),
            "comment": _clip(table.table_comment),
            "columns": [
                {
                    "name": str(c.column_name),
                    "type": str(c.column_type or c.data_type or ""),
                    "comment": _clip(c.column_comment),
                    "is_pk": bool(c.is_primary_key),
                    "is_fk": bool(c.is_foreign_key),
                }
                for c in selected
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
        table.semantic_tags = dumps(ai.get("semantic_tags") or [])
        table.business_terms = dumps(ai.get("business_terms") or [])
        table.aliases = dumps(ai.get("aliases") or [])
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
            col.semantic_tags = dumps(ac.get("semantic_tags") or [])
            col.business_terms = dumps(ac.get("business_terms") or [])
            col.aliases = dumps(ac.get("aliases") or [])
            col.column_role = str(ac.get("column_role") or "") or None
            col.metric_type = str(ac.get("metric_type") or "") if ac.get("metric_type") else None
            col.is_pii = bool(col.is_pii or ac.get("is_pii", False))
            col.ai_confidence = float(ac.get("ai_confidence", 0))
            col.ai_enriched_at = now

        _sync_domain_tag_from_ai(db, table, ai)


def _sync_domain_tag_from_ai(db: OrmSession, table: SchemaTable, ai: dict[str, Any]) -> None:
    """Write LLM-assigned subject / semantic tags into DomainTagRule so that
    Catalog discovery and schema inspection can use them for domain grouping.

    Rules derived from AI enrichment get priority 20 (bootstrap defaults are 10,
    user-created rules are typically 10 as well).
    """
    subject_area = str(ai.get("subject_area") or "").strip()
    semantic_tags: list[str] = ai.get("semantic_tags") or []

    tags_to_apply: list[str] = []
    if subject_area:
        tags_to_apply.append(subject_area)
    for tag in semantic_tags:
        tag_str = str(tag).strip()
        if tag_str and tag_str not in tags_to_apply:
            tags_to_apply.append(tag_str)

    datasource_id = str(table.data_source_id)
    table_name = str(table.table_name)

    # Only write per-table rules (pattern = table_name) so that the tag is
    # scoped to this table and won't accidentally match unrelated tables.
    existing = {
        rule.tag
        for rule in db.query(DomainTagRule).filter(
            DomainTagRule.data_source_id == datasource_id,
            DomainTagRule.pattern == table_name,
        ).all()
    }

    for tag in tags_to_apply:
        if tag in existing:
            continue
        db.add(DomainTagRule(
            data_source_id=datasource_id,
            pattern=table_name,
            tag=tag,
            priority=20,
        ))


def _update_schema_hashes(tables: list[SchemaTable]) -> None:
    """Update schema_hash after successful enrichment."""
    for table in tables:
        table.schema_hash = compute_schema_hash(table)


def _connected_table_names(db: OrmSession, table: SchemaTable) -> set[str]:
    """Get FK-connected table names."""
    fk_ids = {col.foreign_table_id for col in table.columns or [] if col.is_foreign_key and col.foreign_table_id}
    if not fk_ids:
        return set()
    targets = db.query(SchemaTable).filter(SchemaTable.id.in_(fk_ids)).all()
    return {str(t.table_name) for t in targets}
