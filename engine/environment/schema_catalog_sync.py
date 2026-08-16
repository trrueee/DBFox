"""Sync introspection results (SchemaInventory) into the DBFox system catalog.

Writes to SchemaTable / SchemaColumn so tools and downstream catalog consumers
can discover tables without re-introspecting the live datasource
every time.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from engine.json_codec import JsonCodecError, loads

from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.environment.authoritative_inventory import (
    AuthoritativeInventory,
    SchemaInspectionError,
)
from engine.models import DataSource, SchemaTable, SchemaColumn, SchemaSearchDoc
from engine.environment.inventory import (
    SyncResult,
    TableInventory,
)
from engine.environment.catalog_introspector import inspect_catalog

logger = logging.getLogger("dbfox.environment.schema_catalog_sync")


def _ai_enrich_failure_result() -> dict[str, Any]:
    from engine.ai_index import LLM_ENRICH_FAILED

    return {
        "ai_enriched": False,
        "enriched_count": 0,
        "reason": LLM_ENRICH_FAILED,
        "errors": [LLM_ENRICH_FAILED],
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_string_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = loads(value)
    except JsonCodecError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _table_identity(table_schema: str | None, table_name: str) -> tuple[str, str]:
    return (table_schema or "", table_name)


def _only_unique(values: list[str]) -> str | None:
    return values[0] if len(values) == 1 else None


def bump_catalog_revision(db: Session, datasource_id: str) -> int:
    """Atomically increment and return the search-visible catalog revision.

    Uses one SQL ``UPDATE ... SET catalog_revision = catalog_revision + 1`` so
    concurrent publications cannot lose increments. The caller owns the
    surrounding short publication transaction.
    """

    updated = db.execute(
        text(
            "UPDATE data_sources "
            "SET catalog_revision = catalog_revision + 1 "
            "WHERE id = :datasource_id"
        ),
        {"datasource_id": datasource_id},
    )
    if updated.rowcount != 1:
        raise LookupError(f"Unknown datasource for catalog revision: {datasource_id}")
    revision = db.execute(
        text(
            "SELECT catalog_revision FROM data_sources WHERE id = :datasource_id"
        ),
        {"datasource_id": datasource_id},
    ).scalar_one()
    return int(revision)


def rebuild_search_docs(db: Session, datasource_id: str) -> None:
    """Rebuild all schema_search_docs rows for a datasource based on current SchemaTable/SchemaColumn metadata.
    This generates search text offline using table/column names, types, comments, and any existing AI metadata.
    """
    from engine.ai_index import build_table_search_text, build_column_search_text

    # 1. Delete all existing search docs for this datasource
    db.query(SchemaSearchDoc).filter(SchemaSearchDoc.datasource_id == datasource_id).delete(synchronize_session=False)
    db.flush()

    # 2. Fetch all tables and their columns
    tables = list(
        db.execute(
            select(SchemaTable)
            .options(selectinload(SchemaTable.columns))
            .where(SchemaTable.data_source_id == datasource_id)
        ).scalars()
    )
    foreign_table_ids = {
        str(column.foreign_table_id)
        for table in tables
        for column in table.columns
        if column.is_foreign_key and column.foreign_table_id
    }
    foreign_table_names = {
        str(table_id): str(table_name)
        for table_id, table_name in db.execute(
            select(SchemaTable.id, SchemaTable.table_name).where(
                SchemaTable.id.in_(foreign_table_ids)
            )
        )
    } if foreign_table_ids else {}

    for table in tables:
        tags = _parse_string_list(table.semantic_tags)
        terms = _parse_string_list(table.business_terms)
        aliases = _parse_string_list(table.aliases)

        cols = sorted(list(table.columns or []), key=lambda c: (c.ordinal_position or 0, str(c.column_name)))
        col_names = [str(c.column_name) for c in cols]
        col_descs = {str(c.column_name): c.ai_description for c in cols if c.ai_description}

        # Connected tables
        fk_ids = {
            str(col.foreign_table_id)
            for col in cols
            if col.is_foreign_key and col.foreign_table_id
        }
        relation_text = (
            ", ".join(
                sorted(
                    foreign_table_names[table_id]
                    for table_id in fk_ids
                    if table_id in foreign_table_names
                )
            )
            or None
        )

        search_text = build_table_search_text(
            table_schema=str(table.table_schema or ""),
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
            table_schema=str(table.table_schema or ""),
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
            updated_at=_utcnow(),
        ))

        for col in cols:
            ctags = _parse_string_list(col.semantic_tags)
            cterms = _parse_string_list(col.business_terms)

            col_search_text = build_column_search_text(
                column_name=str(col.column_name),
                table_schema=str(table.table_schema or ""),
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
                table_schema=str(table.table_schema or ""),
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
                updated_at=_utcnow(),
            ))

    db.flush()


class SchemaCatalogSync:
    """Sync authoritative inspection snapshots into DBFox's system catalog."""

    def sync(
        self,
        db: Session,
        datasource_id: str,
        *,
        ai_enrich: bool = False,
        llm_credential_id: str | None = None,
        ai_api_base: str | None = None,
        ai_model_name: str | None = None,
    ) -> SyncResult:
        """Introspect and sync. Returns counts of created/updated/removed."""
        try:
            inventory = inspect_catalog(db, datasource_id)
            if inventory.datasource_id != datasource_id:
                raise SchemaInspectionError(
                    datasource_id,
                    FixedErrorCode.SCHEMA_INSPECTION_FAILED,
                )
        except SchemaInspectionError:
            self._record_inspection_failure(db, datasource_id)
            raise
        except Exception as exc:
            logger.warning("Schema inspection failed (%s)", type(exc).__name__)
            error = SchemaInspectionError(
                datasource_id,
                FixedErrorCode.SCHEMA_INSPECTION_FAILED,
            )
            self._record_inspection_failure(db, datasource_id)
            raise error from None
        return self.sync_authoritative(
            db,
            inventory,
            ai_enrich=ai_enrich,
            llm_credential_id=llm_credential_id,
            ai_api_base=ai_api_base,
            ai_model_name=ai_model_name,
        )

    @staticmethod
    def _record_inspection_failure(db: Session, datasource_id: str) -> None:
        """Persist a bounded, redacted failure state without touching catalog rows."""
        try:
            db.rollback()
            db.query(DataSource).filter(DataSource.id == datasource_id).update(
                {
                    "last_sync_at": _utcnow(),
                    "last_sync_status": "failed",
                    "last_sync_error": fixed_error_message(FixedErrorCode.SCHEMA_SYNC_FAILED),
                }
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Could not record schema inspection failure (%s)", type(exc).__name__)

    def sync_authoritative(
        self,
        db: Session,
        inventory: AuthoritativeInventory,
        *,
        ai_enrich: bool = False,
        llm_credential_id: str | None = None,
        ai_api_base: str | None = None,
        ai_model_name: str | None = None,
    ) -> SyncResult:
        """Reconcile the catalog from one complete, authoritative snapshot.

        The authoritative publication and SearchDoc rebuild are one short
        caller-owned transaction. When AI enrichment is requested, that
        transaction commits first, then enrichment runs in separate short
        transactions outside the publication boundary.
        """
        if not isinstance(inventory, AuthoritativeInventory):
            raise TypeError(
                "SchemaCatalogSync.sync_authoritative requires AuthoritativeInventory."
            )

        try:
            result = self._sync_authoritative(db, inventory)
        except Exception:
            db.rollback()
            raise

        if not ai_enrich:
            return result

        db.commit()
        try:
            from engine.ai_enrich import ai_enrich_catalog
            from engine.llm.config import resolve_product_llm_config_from_credential

            llm_config = (
                resolve_product_llm_config_from_credential(
                    llm_credential_id=llm_credential_id,
                    api_base=ai_api_base,
                    model_name=ai_model_name,
                )
                if llm_credential_id
                else None
            )
            enrich_result = ai_enrich_catalog(
                db,
                inventory.datasource_id,
                llm_config=llm_config,
            )
        except Exception as exc:
            logger.warning("AI enrichment failed (%s)", type(exc).__name__)
            enrich_result = _ai_enrich_failure_result()
        if not isinstance(enrich_result, dict):
            logger.warning(
                "AI enrichment returned an invalid result (%s)",
                type(enrich_result).__name__,
            )
            enrich_result = _ai_enrich_failure_result()
        logger.info(
            "AI enrichment finished: enabled=%s enriched_count=%d failures=%d",
            bool(enrich_result.get("ai_enriched")),
            int(enrich_result.get("enriched_count", 0)),
            len(enrich_result.get("errors", [])),
        )
        result.ai_enrich_result = enrich_result
        return result

    def _sync_authoritative(
        self,
        db: Session,
        inventory: AuthoritativeInventory,
    ) -> SyncResult:
        """Perform the one transaction after authoritative input validation."""

        datasource_id = inventory.datasource_id
        result = SyncResult(datasource_id=datasource_id)

        # Upsert tables
        existing_tables: dict[tuple[str, str], SchemaTable] = {
            _table_identity(t.table_schema, t.table_name): t
            for t in db.query(SchemaTable)
            .filter(SchemaTable.data_source_id == datasource_id)
            .all()
        }
        incoming_table_keys: set[tuple[str, str]] = set()
        existing_columns_by_table: dict[str, dict[str, SchemaColumn]] = {}
        for column in db.execute(
            select(SchemaColumn)
            .join(SchemaTable, SchemaColumn.table_id == SchemaTable.id)
            .where(SchemaTable.data_source_id == datasource_id)
        ).scalars():
            existing_columns_by_table.setdefault(str(column.table_id), {})[
                str(column.column_name)
            ] = column

        for table_inv in inventory.tables:
            table_key = _table_identity(table_inv.table_schema, table_inv.table_name)
            incoming_table_keys.add(table_key)
            schema_table = existing_tables.get(table_key)
            if schema_table is None:
                schema_table = SchemaTable(
                    id=str(uuid.uuid4()),
                    data_source_id=datasource_id,
                    table_schema=table_inv.table_schema or "",
                    table_name=table_inv.table_name,
                    table_comment=table_inv.comment,
                    table_type=table_inv.table_type,
                    row_count_estimate=table_inv.row_count_estimate,
                    engine_name=inventory.dialect,
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
                db.add(schema_table)
                result.tables_created += 1
            else:
                schema_table.table_schema = table_inv.table_schema or ""
                schema_table.table_name = table_inv.table_name
                schema_table.table_comment = table_inv.comment
                schema_table.table_type = table_inv.table_type
                schema_table.row_count_estimate = table_inv.row_count_estimate
                schema_table.engine_name = inventory.dialect
                schema_table.updated_at = _utcnow()
                result.tables_updated += 1

            db.flush()  # populate schema_table.id for FK
            existing_tables[table_key] = schema_table

            # Upsert columns
            self._sync_columns(
                db,
                schema_table.id,
                table_inv,
                result,
                existing_columns=existing_columns_by_table.get(str(schema_table.id), {}),
            )

        # Remove tables that no longer exist in the live datasource
        removed_keys = set(existing_tables.keys()) - incoming_table_keys
        for removed_key in removed_keys:
            removed_table = existing_tables[removed_key]
            db.query(SchemaColumn).filter(
                SchemaColumn.table_id == removed_table.id
            ).delete()
            db.delete(removed_table)
            result.tables_removed += 1

        # Resolve foreign keys
        all_tables = list(
            db.execute(
                select(SchemaTable)
                .options(selectinload(SchemaTable.columns))
                .where(SchemaTable.data_source_id == datasource_id)
            ).scalars()
        )
        table_key_to_id = {_table_identity(t.table_schema, t.table_name): t.id for t in all_tables}
        table_ids_by_name: dict[str, list[str]] = {}

        column_name_to_id: dict[tuple[str, str, str], str] = {}
        column_ids_by_name: dict[tuple[str, str], list[str]] = {}
        column_objects: dict[tuple[str, str, str], SchemaColumn] = {}
        for t in all_tables:
            table_key = _table_identity(t.table_schema, t.table_name)
            table_ids_by_name.setdefault(t.table_name, []).append(t.id)
            for col in t.columns:
                column_key = (*table_key, col.column_name)
                column_name_to_id[column_key] = col.id
                column_ids_by_name.setdefault((t.table_name, col.column_name), []).append(col.id)
                column_objects[column_key] = col

        # Reset foreign key fields first (in case some were removed)
        for col in column_objects.values():
            col.is_foreign_key = False
            col.foreign_table_id = None
            col.foreign_column_id = None

        # Set foreign keys from inventory
        for table_inv in inventory.tables:
            table_key = _table_identity(table_inv.table_schema, table_inv.table_name)
            for fk in table_inv.foreign_keys:
                c_name = fk.column_name
                ref_t_name = fk.referenced_table
                ref_c_name = fk.referenced_column
                ref_schema = getattr(fk, "referenced_schema", None) or table_key[0]
                ref_table_key = _table_identity(ref_schema, ref_t_name)

                fk_col = column_objects.get((*table_key, c_name))
                ref_table_id = table_key_to_id.get(ref_table_key)
                ref_col_id = column_name_to_id.get((*ref_table_key, ref_c_name))

                if ref_table_id is None:
                    ref_table_id = _only_unique(table_ids_by_name.get(ref_t_name, []))
                if ref_col_id is None:
                    ref_col_id = _only_unique(column_ids_by_name.get((ref_t_name, ref_c_name), []))

                if fk_col and ref_table_id and ref_col_id:
                    fk_col.is_foreign_key = True
                    fk_col.foreign_table_id = ref_table_id
                    fk_col.foreign_column_id = ref_col_id

        # Rebuild schema search docs immediately
        rebuild_search_docs(db, datasource_id)

        refreshed_at = _utcnow()
        datasource = db.get(DataSource, datasource_id)
        if datasource is not None:
            datasource.last_sync_at = refreshed_at
            datasource.last_sync_status = "ready"
            datasource.last_sync_error = None
        db.flush()
        result.catalog_revision = bump_catalog_revision(db, datasource_id)
        if datasource is not None:
            db.expire(datasource, ["catalog_revision"])
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

        return result

    def _sync_columns(
        self,
        db: Session,
        table_id: str,
        table_inv: TableInventory,
        result: SyncResult,
        *,
        existing_columns: dict[str, SchemaColumn],
    ) -> None:
        existing_cols = existing_columns
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
    llm_credential_id: str | None = None,
    ai_api_base: str | None = None,
    ai_model_name: str | None = None,
) -> SyncResult:
    """Refresh and commit one complete application-level catalog transaction."""
    result = SchemaCatalogSync().sync(
        db,
        datasource_id,
        ai_enrich=ai_enrich,
        llm_credential_id=llm_credential_id,
        ai_api_base=ai_api_base,
        ai_model_name=ai_model_name,
    )
    db.commit()
    return result
