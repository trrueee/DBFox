"""Typed data models for schema introspection results."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class ColumnInventory(BaseModel):
    column_name: str
    data_type: str | None = None
    column_type: str | None = None
    is_nullable: bool = True
    column_default: str | None = None
    is_primary_key: bool = False
    is_foreign_key: bool = False


class ForeignKeyInventory(BaseModel):
    column_name: str
    referenced_table: str
    referenced_column: str


class TableInventory(BaseModel):
    table_name: str
    table_schema: str = ""
    table_type: str = "table"
    comment: str | None = None
    columns: list[ColumnInventory] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyInventory] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count_estimate: int | None = None


class SchemaInventory(BaseModel):
    datasource_id: str
    dialect: str
    database_name: str = ""
    tables: list[TableInventory] = Field(default_factory=list)
    table_count: int = 0
    column_count: int = 0


class SyncResult(BaseModel):
    datasource_id: str
    tables_created: int = 0
    tables_updated: int = 0
    tables_removed: int = 0
    columns_created: int = 0
    columns_updated: int = 0
    columns_removed: int = 0
    synced: bool = False
