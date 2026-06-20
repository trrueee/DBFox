"""
.. deprecated::
    All sync callers now go through ``ensure_catalog()``
    (``engine.environment.schema_catalog_sync``).  This wrapper delegates to
    ``ensure_catalog`` and converts the result to the legacy dict format for
    backward compatibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from engine.environment.schema_catalog_sync import ensure_catalog
from engine.environment.inventory import SyncResult
from engine.errors import DataSourceConnectionError
from engine.models import DataSource


def sync_schema(db: Session, datasource_id: str, **kwargs: Any) -> dict[str, Any]:
    """Unified schema sync — delegates to ``ensure_catalog()``.

    SQLite guard: refuses missing files.
    """
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise DataSourceConnectionError("Data source not found")

    if ds.db_type == "sqlite":
        path = Path(str(ds.database_name or "")).expanduser()
        if not path.is_file():
            raise DataSourceConnectionError(
                f"SQLite database file does not exist: {path}"
            )

    ai_enrich = kwargs.pop("ai_enrich", False)
    result: SyncResult = ensure_catalog(db, datasource_id, ai_enrich=ai_enrich)
    return {
        "ok": result.synced,
        "tablesSynced": (result.tables_created or 0) + (result.tables_updated or 0),
        "tablesDropped": result.tables_removed or 0,
        "synced": result.synced,
    }
