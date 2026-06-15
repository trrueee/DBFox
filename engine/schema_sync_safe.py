from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from engine.errors import DataSourceConnectionError
from engine.models import DataSource
from engine.schema_sync import sync_schema as _legacy_sync_schema


def sync_schema(db: Session, datasource_id: str) -> dict[str, Any]:
    """Safer schema sync entry point used by the API.

    - SQLite: refuses missing files so sync cannot create an empty database.
    - PostgreSQL / MySQL: delegates to the existing implementation (which now
      carries datasource SSL settings into the connection).
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
        return _legacy_sync_schema(db, datasource_id)

    return _legacy_sync_schema(db, datasource_id)
