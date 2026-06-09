"""Resolve a datasource_id into a uniform ResolvedDataSource model."""
from __future__ import annotations

from typing import Literal
from sqlalchemy.orm import Session
from pydantic import BaseModel

from engine.models import DataSource


class ResolvedDataSource(BaseModel):
    datasource_id: str
    name: str | None = None
    dialect: Literal["mysql", "postgres", "sqlite", "duckdb"]
    connection_kind: Literal["network", "file", "memory"]
    database_path: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    safe_display_name: str = ""


def resolve_datasource(db: Session, datasource_id: str) -> ResolvedDataSource:
    """Build a uniform ResolvedDataSource from the catalog row."""
    row = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if row is None:
        raise ValueError(f"Datasource not found: {datasource_id}")

    db_type = (row.db_type or "mysql").lower()
    dialect: Literal["mysql", "postgres", "sqlite", "duckdb"]
    if "postgres" in db_type:
        dialect = "postgres"
    elif "sqlite" in db_type:
        dialect = "sqlite"
    elif "duckdb" in db_type:
        dialect = "duckdb"
    else:
        dialect = "mysql"

    # Determine connection kind
    database_path: str | None = None
    connection_kind: Literal["network", "file", "memory"] = "network"
    if dialect == "sqlite":
        database_path = str(row.database_name or "")
        connection_kind = "memory" if database_path == ":memory:" else "file"

    safe_display_name = (
        row.name or f"{dialect}://{row.host or 'localhost'}/{row.database_name or 'unknown'}"
    )

    return ResolvedDataSource(
        datasource_id=datasource_id,
        name=row.name,
        dialect=dialect,
        connection_kind=connection_kind,
        database_path=database_path,
        host=str(row.host) if row.host else None,
        port=int(row.port) if row.port else None,
        database=str(row.database_name) if row.database_name else None,
        username=str(row.username) if row.username else None,
        safe_display_name=safe_display_name,
    )
