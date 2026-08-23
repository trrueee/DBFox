"""Legacy Core metadata loader for the Data DLC dialect value contract.

Delete this boundary when Data execution resolves ``DatabaseResource`` from
the System DLC state instead of the legacy Core ``DataSource`` table.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from dlcs.dbfox_data.backend.sql.dialect_context import (
    DatabaseDialectContext,
    canonical_sql_dialect,
)
from engine.models import DataSource


def dialect_context_from_datasource(datasource: DataSource) -> DatabaseDialectContext:
    return DatabaseDialectContext(
        resource_id=str(datasource.id),
        dialect=canonical_sql_dialect(str(datasource.db_type or "mysql")),
    )


def load_dialect_context(db: Session, resource_id: str) -> DatabaseDialectContext:
    datasource = db.query(DataSource).filter(DataSource.id == resource_id).first()
    if datasource is None:
        return DatabaseDialectContext(resource_id=resource_id, dialect="mysql")
    return dialect_context_from_datasource(datasource)
