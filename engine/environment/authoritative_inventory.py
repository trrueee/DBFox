"""Authoritative schema inspection results and typed inspection failures.

An inspection is either a complete snapshot that can safely drive destructive
catalog reconciliation, or it fails.  In particular, connectivity and path
errors must never look like a successfully inspected empty database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from dlcs.dbfox_data.backend.inventory import SchemaInventory, TableInventory
from engine.errors import DBFoxError


class SchemaInspectionError(DBFoxError):
    """A live datasource could not produce a complete schema snapshot."""

    def __init__(
        self,
        datasource_id: str,
        code: FixedErrorCode = FixedErrorCode.SCHEMA_INSPECTION_FAILED,
    ) -> None:
        super().__init__(fixed_error_message(code), code=code.value)
        self.datasource_id = datasource_id


@dataclass(frozen=True)
class AuthoritativeInventory:
    """A fully captured schema snapshot eligible for catalog reconciliation."""

    database_resource_id: str
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
            database_resource_id=inventory.database_resource_id,
            generation=generation,
            tables=tuple(table.model_copy(deep=True) for table in inventory.tables),
            captured_at=captured_at or datetime.now(UTC),
            dialect=inventory.dialect,
            database_name=inventory.database_name,
        )
