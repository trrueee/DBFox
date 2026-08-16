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
    column_comment: str | None = None


class ForeignKeyInventory(BaseModel):
    column_name: str
    referenced_table: str
    referenced_column: str
    referenced_schema: str | None = None


class TableInventory(BaseModel):
    table_name: str
    table_schema: str = ""
    table_type: str = "table"
    comment: str | None = None
    columns: list[ColumnInventory] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyInventory] = Field(default_factory=list)
    row_count_estimate: int | None = None


class ForeignKeyReference(BaseModel):
    schema_name: str | None = None
    table: str
    column: str


class InspectedColumn(BaseModel):
    name: str
    type: str
    nullable: bool
    default: str | None = None
    primary_key: bool = False
    foreign_key: ForeignKeyReference | None = None
    comment: str | None = None


class OutgoingForeignKey(BaseModel):
    column: str
    references: ForeignKeyReference


class IncomingForeignKey(BaseModel):
    schema_name: str | None = None
    table: str
    column: str
    references: ForeignKeyReference


class InspectedIndex(BaseModel):
    name: str
    columns: list[str] = Field(default_factory=list)
    unique: bool = False


class InspectedTable(BaseModel):
    object_type: Literal["table"] = "table"
    name: str
    schema_name: str | None = None
    type: Literal["table", "view"]
    dialect: str
    comment: str | None = None
    row_estimate: int | None = None
    columns: list[InspectedColumn] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys_out: list[OutgoingForeignKey] = Field(default_factory=list)
    foreign_keys_in: list[IncomingForeignKey] = Field(default_factory=list)
    indexes: list[InspectedIndex] = Field(default_factory=list)
    source: Literal["live"] = "live"


class InspectedColumnObject(InspectedColumn):
    object_type: Literal["column"] = "column"
    table: str
    schema_name: str | None = None
    dialect: str
    source: Literal["live"] = "live"


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
    catalog_revision: int | None = None
    ai_enrich_result: dict[str, Any] | None = None
