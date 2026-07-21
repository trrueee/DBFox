"""Authoritative schema inspection results and typed inspection failures.

An inspection is either a complete snapshot that can safely drive destructive
catalog reconciliation, or it fails.  In particular, connectivity and path
errors must never look like a successfully inspected empty database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from engine.environment.inventory import SchemaInventory, TableInventory
from engine.errors import DBFoxError


class SchemaInspectionErrorCode(str, Enum):
    """Stable, non-secret reasons why an inspection could not complete."""

    DATASOURCE_NOT_FOUND = "SCHEMA_DATASOURCE_NOT_FOUND"
    SQLITE_PATH_UNAVAILABLE = "SCHEMA_SQLITE_PATH_UNAVAILABLE"
    DUCKDB_PATH_UNAVAILABLE = "SCHEMA_DUCKDB_PATH_UNAVAILABLE"
    DUCKDB_MEMORY_UNSUPPORTED = "SCHEMA_DUCKDB_MEMORY_UNSUPPORTED"
    CONNECTION_FAILED = "SCHEMA_CONNECTION_FAILED"
    CREDENTIAL_UNAVAILABLE = "SCHEMA_CREDENTIAL_UNAVAILABLE"
    SSH_FAILED = "SCHEMA_SSH_FAILED"
    TLS_FAILED = "SCHEMA_TLS_FAILED"
    INSPECTION_FAILED = "SCHEMA_INSPECTION_FAILED"


class SchemaInspectionError(DBFoxError):
    """A live datasource could not produce a complete schema snapshot."""

    def __init__(
        self,
        datasource_id: str,
        code: SchemaInspectionErrorCode = SchemaInspectionErrorCode.INSPECTION_FAILED,
    ) -> None:
        super().__init__("Schema inspection could not be completed.", code=code)
        self.datasource_id = datasource_id


@dataclass(frozen=True)
class AuthoritativeInventory:
    """A fully captured schema snapshot eligible for catalog reconciliation."""

    datasource_id: str
    generation: int
    tables: tuple[TableInventory, ...]
    captured_at: datetime
    dialect: str = ""
    database_name: str = ""

    @property
    def table_count(self) -> int:
        return len(self.tables)

    @property
    def column_count(self) -> int:
        return sum(len(table.columns) for table in self.tables)

    @classmethod
    def from_completed_inventory(
        cls,
        inventory: SchemaInventory,
        *,
        generation: int = 0,
        captured_at: datetime | None = None,
    ) -> "AuthoritativeInventory":
        """Freeze a completed inspector result before any catalog mutation."""
        return cls(
            datasource_id=inventory.datasource_id,
            generation=generation,
            tables=tuple(table.model_copy(deep=True) for table in inventory.tables),
            captured_at=captured_at or datetime.now(UTC),
            dialect=inventory.dialect,
            database_name=inventory.database_name,
        )
