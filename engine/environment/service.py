"""EnvironmentService — unified entry point for deterministic datasource facts.

Aggregates information from datasource config (via datasource_resolver) and
the DBFox system catalog (SchemaTable / SchemaColumn) into structured
profiles and snapshots.  No LLM involvement.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from engine.models import SchemaTable, SchemaColumn, DataSource
from engine.environment.datasource_resolver import resolve_datasource
from engine.environment.models import (
    CatalogSnapshot,
    ColumnSnapshot,
    DataEnvironmentProfile,
    ForeignKeySnapshot,
    TableSnapshot,
)
from engine.environment.inventory import SyncResult
from engine.environment.schema_catalog_sync import ensure_catalog

logger = logging.getLogger("dbfox.environment.service")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EnvironmentService:
    """Provides deterministic facts about a datasource for the Agent.

    Usage:
        svc = EnvironmentService()
        profile = svc.get_profile(db, datasource_id)
        snapshot = svc.get_catalog_snapshot(db, datasource_id, selected_tables=["orders"])
    """

    # ------------------------------------------------------------------
    # get_profile
    # ------------------------------------------------------------------

    def get_profile(
        self,
        db: Session,
        datasource_id: str,
        *,
        selected_tables: list[str] | None = None,
    ) -> DataEnvironmentProfile:
        """Build a DataEnvironmentProfile from datasource config + catalog."""
        try:
            resolved = resolve_datasource(db, datasource_id)
        except ValueError:
            return DataEnvironmentProfile(
                datasource_id=datasource_id,
                env="unknown",
                dialect="unknown",
                catalog_status="unknown",
                warnings=[f"Datasource {datasource_id} not found in config."],
            )

        # Determine environment tier from datasource name / config
        env = self._infer_env(resolved)

        # Count tables in catalog
        table_count = (
            db.query(SchemaTable)
            .filter(SchemaTable.data_source_id == datasource_id)
            .count()
        )

        # Determine catalog status
        catalog_status = self._catalog_status(table_count)

        # Gather warnings
        warnings: list[str] = []
        if catalog_status == "empty":
            warnings.append("Catalog is empty. Run schema.refresh_catalog to introspect the datasource.")
        if catalog_status == "stale":
            warnings.append("Catalog may be stale. Consider running schema.refresh_catalog.")
        if env == "prod":
            warnings.append("This is a PRODUCTION datasource. Read-only operations only.")

        return DataEnvironmentProfile(
            datasource_id=datasource_id,
            env=env,
            dialect=resolved.dialect,
            database_name=resolved.database or resolved.database_path,
            catalog_status=catalog_status,
            table_count=table_count,
            selected_tables=selected_tables or [],
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # get_catalog_snapshot
    # ------------------------------------------------------------------

    def get_catalog_snapshot(
        self,
        db: Session,
        datasource_id: str,
        *,
        selected_tables: list[str] | None = None,
    ) -> CatalogSnapshot:
        """Build a CatalogSnapshot from the system catalog."""
        query = db.query(SchemaTable).filter(
            SchemaTable.data_source_id == datasource_id
        )
        if selected_tables:
            query = query.filter(SchemaTable.table_name.in_(selected_tables))

        tables = query.order_by(SchemaTable.table_name).all()

        table_count = len(tables)
        catalog_status = self._catalog_status(table_count)

        snapshots: list[TableSnapshot] = []
        relationships: list[ForeignKeySnapshot] = []

        for table in tables:
            columns = (
                db.query(SchemaColumn)
                .filter(SchemaColumn.table_id == table.id)
                .order_by(SchemaColumn.column_name)
                .all()
            )

            col_snapshots: list[ColumnSnapshot] = []
            for col in columns:
                col_snapshots.append(
                    ColumnSnapshot(
                        column_name=col.column_name,
                        data_type=str(col.data_type or ""),
                        is_nullable=bool(col.is_nullable),
                        is_primary_key=bool(col.is_primary_key),
                        is_foreign_key=bool(col.is_foreign_key),
                        column_default=str(col.column_default) if col.column_default else None,
                    )
                )

                # Collect FK relationships
                if col.is_foreign_key and col.foreign_table_id:
                    ref_table = (
                        db.query(SchemaTable)
                        .filter(SchemaTable.id == col.foreign_table_id)
                        .first()
                    )
                    if ref_table:
                        ref_col_name = "id"
                        if col.foreign_column_id:
                            ref_col = (
                                db.query(SchemaColumn)
                                .filter(SchemaColumn.id == col.foreign_column_id)
                                .first()
                            )
                            if ref_col:
                                ref_col_name = ref_col.column_name
                        relationships.append(
                            ForeignKeySnapshot(
                                source_table=table.table_name,
                                column_name=col.column_name,
                                referenced_table=ref_table.table_name,
                                referenced_column=ref_col_name,
                            )
                        )

            snapshots.append(
                TableSnapshot(
                    table_name=table.table_name,
                    table_type=str(table.table_type or "table"),
                    row_count_estimate=table.row_count_estimate,
                    column_count=len(col_snapshots),
                    columns=col_snapshots,
                    comment=str(table.table_comment) if table.table_comment else None,
                )
            )

        return CatalogSnapshot(
            datasource_id=datasource_id,
            catalog_status=catalog_status,
            tables=snapshots,
            relationships=relationships,
            generated_at=_utcnow(),
        )

    # ------------------------------------------------------------------
    # ensure_catalog
    # ------------------------------------------------------------------

    def ensure_catalog(self, db: Session, datasource_id: str, reason: str = "") -> SyncResult:
        """Introspect and sync the datasource catalog."""
        return ensure_catalog(db, datasource_id)

    # ------------------------------------------------------------------
    # describe_table
    # ------------------------------------------------------------------

    def describe_table(
        self,
        db: Session,
        datasource_id: str,
        table_name: str,
    ) -> TableSnapshot | None:
        """Look up a single table from the catalog."""
        table = (
            db.query(SchemaTable)
            .filter(
                SchemaTable.data_source_id == datasource_id,
                SchemaTable.table_name == table_name,
            )
            .first()
        )
        if table is None:
            return None

        columns = (
            db.query(SchemaColumn)
            .filter(SchemaColumn.table_id == table.id)
            .order_by(SchemaColumn.column_name)
            .all()
        )

        col_snapshots = [
            ColumnSnapshot(
                column_name=c.column_name,
                data_type=str(c.data_type or ""),
                is_nullable=bool(c.is_nullable),
                is_primary_key=bool(c.is_primary_key),
                is_foreign_key=bool(c.is_foreign_key),
                column_default=str(c.column_default) if c.column_default else None,
            )
            for c in columns
        ]

        return TableSnapshot(
            table_name=table.table_name,
            table_type=str(table.table_type or "table"),
            row_count_estimate=table.row_count_estimate,
            column_count=len(col_snapshots),
            columns=col_snapshots,
            comment=str(table.table_comment) if table.table_comment else None,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_env(resolved) -> str:
        """Infer environment tier from datasource name or host."""
        name_lower = (resolved.name or "").lower()
        host_lower = (resolved.host or "").lower()
        db_lower = (resolved.database or "").lower()

        prod_indicators = ["prod", "production", "live", "online"]
        staging_indicators = ["stag", "staging", "uat", "qa", "test"]
        dev_indicators = ["dev", "local", "localhost", "127.0.0.1"]

        combined = f"{name_lower} {host_lower} {db_lower}"

        if any(ind in combined for ind in prod_indicators):
            return "prod"
        if any(ind in combined for ind in staging_indicators):
            return "staging"
        if any(ind in combined for ind in dev_indicators):
            return "dev"
        return "unknown"

    @staticmethod
    @staticmethod
    def _catalog_status(table_count: int) -> str:
        """Derive initial catalog status from table count only.

        Staleness is tracked separately via ``DataSource.last_sync_status``
        and ``last_sync_at`` — this helper only distinguishes empty from
        non-empty catalogs.
        """
        return "empty" if table_count == 0 else "fresh"
