"""Sync introspection results (SchemaInventory) into the DBFox system catalog.

Writes to SchemaTable / SchemaColumn so that SchemaLinker and downstream
tools can discover tables without re-introspecting the live datasource
every time.
"""
from __future__ import annotations

import logging
import uuid
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from engine.models import SchemaTable, SchemaColumn, SchemaSearchDoc
from engine.environment.inventory import (
    SchemaInventory,
    SyncResult,
    TableInventory,
)
from engine.environment.schema_introspector import introspect_datasource

logger = logging.getLogger("dbfox.environment.schema_catalog_sync")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def rebuild_search_docs(db: Session, datasource_id: str) -> None:
    """Rebuild all schema_search_docs rows for a datasource based on current SchemaTable/SchemaColumn metadata.
    This generates search text offline using table/column names, types, comments, and any existing AI metadata.
    """
    from engine.ai_index import build_table_search_text, build_column_search_text

    # 1. Delete all existing search docs for this datasource
    db.query(SchemaSearchDoc).filter(SchemaSearchDoc.datasource_id == datasource_id).delete(synchronize_session=False)
    db.flush()

    # 2. Fetch all tables and their columns
    tables = db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()

    for table in tables:
        # Load and parse lists from JSON strings safely
        def _parse_list(s: str | None) -> list[str]:
            if not s:
                return []
            try:
                val = json.loads(s)
                if isinstance(val, list):
                    return [str(x) for x in val]
            except Exception:
                pass
            return []

        tags = _parse_list(table.semantic_tags)
        terms = _parse_list(table.business_terms)
        aliases = _parse_list(table.aliases)

        cols = sorted(list(table.columns or []), key=lambda c: (c.ordinal_position or 0, str(c.column_name)))
        col_names = [str(c.column_name) for c in cols]
        col_descs = {str(c.column_name): c.ai_description for c in cols if c.ai_description}

        # Connected tables
        fk_ids = {col.foreign_table_id for col in cols if col.is_foreign_key and col.foreign_table_id}
        relation_text = None
        if fk_ids:
            targets = db.query(SchemaTable.table_name).filter(SchemaTable.id.in_(fk_ids)).all()
            relation_text = ", ".join(sorted(str(t[0]) for t in targets)) or None

        search_text = build_table_search_text(
            table_name=str(table.table_name),
            ai_description=table.ai_description,
            semantic_tags=tags,
            business_terms=terms,
            aliases=aliases,
            table_role=table.table_role,
            grain=table.grain,
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
            ai_description=table.ai_description,
            semantic_tags=table.semantic_tags,
            business_terms=table.business_terms,
            aliases=table.aliases,
            table_role=table.table_role,
            grain=table.grain,
            subject_area=table.subject_area,
            column_summary=", ".join(col_names),
            relation_summary=relation_text,
            search_text=search_text,
            ai_confidence=table.ai_confidence,
            updated_at=utcnow(),
        ))

        for col in cols:
            ctags = _parse_list(col.semantic_tags)
            cterms = _parse_list(col.business_terms)

            col_search_text = build_column_search_text(
                column_name=str(col.column_name),
                table_name=str(table.table_name),
                ai_description=col.ai_description,
                semantic_tags=ctags,
                business_terms=cterms,
                column_role=col.column_role,
                metric_type=col.metric_type,
            )

            db.add(SchemaSearchDoc(
                datasource_id=datasource_id,
                entity_type="column",
                entity_id=str(col.id),
                table_name=str(table.table_name),
                column_name=str(col.column_name),
                name=str(col.column_name),
                ai_description=col.ai_description,
                semantic_tags=col.semantic_tags,
                business_terms=col.business_terms,
                aliases=col.aliases,
                column_role=col.column_role,
                metric_type=col.metric_type,
                column_summary=None,
                relation_summary=None,
                search_text=col_search_text,
                ai_confidence=col.ai_confidence,
                updated_at=utcnow(),
            ))

    db.flush()


class SchemaCatalogSync:
    """Sync a SchemaInventory into DBFox's system catalog."""

    def sync(
        self,
        db: Session,
        datasource_id: str,
        *,
        ai_enrich: bool = False,
        ai_api_key: str | None = None,
        ai_api_base: str | None = None,
        ai_model_name: str | None = None,
    ) -> SyncResult:
        """Introspect and sync. Returns counts of created/updated/removed."""
        inventory = introspect_datasource(db, datasource_id)
        return self.sync_inventory(
            db,
            datasource_id,
            inventory,
            ai_enrich=ai_enrich,
            ai_api_key=ai_api_key,
            ai_api_base=ai_api_base,
            ai_model_name=ai_model_name,
        )

    def sync_inventory(
        self,
        db: Session,
        datasource_id: str,
        inventory: SchemaInventory,
        *,
        ai_enrich: bool = False,
        ai_api_key: str | None = None,
        ai_api_base: str | None = None,
        ai_model_name: str | None = None,
    ) -> SyncResult:
        result = SyncResult(datasource_id=datasource_id)

        # Upsert tables
        existing_tables: dict[str, SchemaTable] = {
            t.table_name: t
            for t in db.query(SchemaTable)
            .filter(SchemaTable.data_source_id == datasource_id)
            .all()
        }
        incoming_names: set[str] = set()

        for table_inv in inventory.tables:
            incoming_names.add(table_inv.table_name)
            schema_table = existing_tables.get(table_inv.table_name)
            if schema_table is None:
                schema_table = SchemaTable(
                    id=str(uuid.uuid4()),
                    data_source_id=datasource_id,
                    table_schema=table_inv.table_schema or "",
                    table_name=table_inv.table_name,
                    table_comment=table_inv.comment,
                    table_type=table_inv.table_type,
                    row_count_estimate=table_inv.row_count_estimate or 0,
                    engine_name=inventory.dialect,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
                db.add(schema_table)
                result.tables_created += 1
            else:
                schema_table.table_comment = table_inv.comment
                schema_table.table_type = table_inv.table_type
                schema_table.row_count_estimate = table_inv.row_count_estimate or 0
                schema_table.engine_name = inventory.dialect
                schema_table.updated_at = utcnow()
                result.tables_updated += 1

            db.flush()  # populate schema_table.id for FK

            # Upsert columns
            self._sync_columns(db, schema_table.id, table_inv, result)

        # Remove tables that no longer exist in the live datasource
        removed_names = set(existing_tables.keys()) - incoming_names
        for removed_name in removed_names:
            removed_table = existing_tables[removed_name]
            db.query(SchemaColumn).filter(
                SchemaColumn.table_id == removed_table.id
            ).delete()
            db.delete(removed_table)
            result.tables_removed += 1

        # Resolve foreign keys
        all_tables = db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()
        table_name_to_id = {t.table_name: t.id for t in all_tables}

        column_name_to_id: dict[tuple[str, str], str] = {}
        column_objects: dict[tuple[str, str], SchemaColumn] = {}
        for t in all_tables:
            for col in t.columns:
                column_name_to_id[(t.table_name, col.column_name)] = col.id
                column_objects[(t.table_name, col.column_name)] = col

        # Reset foreign key fields first (in case some were removed)
        for col in column_objects.values():
            col.is_foreign_key = False
            col.foreign_table_id = None
            col.foreign_column_id = None

        # Set foreign keys from inventory
        for table_inv in inventory.tables:
            t_name = table_inv.table_name
            for fk in table_inv.foreign_keys:
                c_name = fk.column_name
                ref_t_name = fk.referenced_table
                ref_c_name = fk.referenced_column

                fk_col = column_objects.get((t_name, c_name))
                ref_table_id = table_name_to_id.get(ref_t_name)
                ref_col_id = column_name_to_id.get((ref_t_name, ref_c_name))

                if fk_col and ref_table_id and ref_col_id:
                    fk_col.is_foreign_key = True
                    fk_col.foreign_table_id = ref_table_id
                    fk_col.foreign_column_id = ref_col_id

        # Rebuild schema search docs immediately
        rebuild_search_docs(db, datasource_id)

        db.commit()
        result.synced = True
        logger.info(
            "SchemaCatalogSync %s: +%d ~%d -%d tables, +%d ~%d -%d columns",
            datasource_id,
            result.tables_created,
            result.tables_updated,
            result.tables_removed,
            result.columns_created,
            result.columns_updated,
            result.columns_removed,
        )

        if ai_enrich:
            from engine.ai_enrich import ai_enrich_catalog
            from engine.llm.config import resolve_optional_product_llm_config

            llm_config = resolve_optional_product_llm_config(
                api_key=ai_api_key,
                api_base=ai_api_base,
                model_name=ai_model_name,
            )
            enrich_result = ai_enrich_catalog(
                db,
                datasource_id,
                llm_config=llm_config,
            )
            logger.info("AI enrich: %s", enrich_result)
            result.ai_enrich_result = enrich_result

        return result

    def _sync_columns(
        self,
        db: Session,
        table_id: str,
        table_inv: TableInventory,
        result: SyncResult,
    ) -> None:
        existing_cols: dict[str, SchemaColumn] = {
            c.column_name: c
            for c in db.query(SchemaColumn)
            .filter(SchemaColumn.table_id == table_id)
            .all()
        }
        incoming_col_names: set[str] = set()

        for col_inv in table_inv.columns:
            incoming_col_names.add(col_inv.column_name)
            sc = existing_cols.get(col_inv.column_name)
            if sc is None:
                sc = SchemaColumn(
                    id=str(uuid.uuid4()),
                    table_id=table_id,
                    column_name=col_inv.column_name,
                    data_type=col_inv.data_type,
                    column_type=col_inv.column_type,
                    is_nullable=col_inv.is_nullable,
                    column_default=col_inv.column_default,
                    is_primary_key=col_inv.is_primary_key,
                    is_foreign_key=col_inv.is_foreign_key,
                    column_comment=col_inv.column_comment,
                )
                db.add(sc)
                result.columns_created += 1
            else:
                sc.data_type = col_inv.data_type
                sc.column_type = col_inv.column_type
                sc.is_nullable = col_inv.is_nullable
                sc.column_default = col_inv.column_default
                sc.is_primary_key = col_inv.is_primary_key
                sc.is_foreign_key = col_inv.is_foreign_key
                sc.column_comment = col_inv.column_comment
                result.columns_updated += 1

        # Remove stale columns
        removed = set(existing_cols.keys()) - incoming_col_names
        for col_name in removed:
            db.delete(existing_cols[col_name])
            result.columns_removed += 1


def ensure_catalog(
    db: Session,
    datasource_id: str,
    *,
    ai_enrich: bool = False,
    ai_api_key: str | None = None,
    ai_api_base: str | None = None,
    ai_model_name: str | None = None,
) -> SyncResult:
    """Introspect and sync if the catalog is empty for this datasource.

    Safe to call before schema linking — if tables already exist
    it will still refresh (upsert).
    """
    return SchemaCatalogSync().sync(
        db,
        datasource_id,
        ai_enrich=ai_enrich,
        ai_api_key=ai_api_key,
        ai_api_base=ai_api_base,
        ai_model_name=ai_model_name,
    )
