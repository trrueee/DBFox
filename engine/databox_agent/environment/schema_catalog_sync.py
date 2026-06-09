"""Sync introspection results (SchemaInventory) into the DataBox system catalog.

Writes to SchemaTable / SchemaColumn so that SchemaLinker and downstream
tools can discover tables without re-introspecting the live datasource
every time.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from engine.models import SchemaTable, SchemaColumn
from engine.databox_agent.environment.schema_inventory import (
    SchemaInventory,
    SyncResult,
    TableInventory,
)
from engine.databox_agent.environment.schema_introspector import introspect_datasource

logger = logging.getLogger("databox.environment.schema_catalog_sync")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SchemaCatalogSync:
    """Sync a SchemaInventory into DataBox's system catalog."""

    def sync(self, db: Session, datasource_id: str) -> SyncResult:
        """Introspect and sync.  Returns counts of created/updated/removed."""
        inventory = introspect_datasource(db, datasource_id)
        return self.sync_inventory(db, datasource_id, inventory)

    def sync_inventory(
        self, db: Session, datasource_id: str, inventory: SchemaInventory
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
                    column_comment="",
                )
                db.add(sc)
                result.columns_created += 1
            else:
                sc.data_type = col_inv.data_type
                sc.column_type = col_inv.column_type
                sc.is_nullable = col_inv.is_nullable
                sc.is_primary_key = col_inv.is_primary_key
                sc.is_foreign_key = col_inv.is_foreign_key
                result.columns_updated += 1

        # Remove stale columns
        removed = set(existing_cols.keys()) - incoming_col_names
        for col_name in removed:
            db.delete(existing_cols[col_name])
            result.columns_removed += 1


def ensure_catalog(db: Session, datasource_id: str) -> SyncResult:
    """Introspect and sync if the catalog is empty for this datasource.

    Safe to call before schema.build_context — if tables already exist
    it will still refresh (upsert).
    """
    return SchemaCatalogSync().sync(db, datasource_id)
