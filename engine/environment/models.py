"""Environment data models for DBFox Agent.

These models represent persisted datasource environment facts. Catalog rows may
include schema-doc AI enrichment, but this layer does not call an LLM itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EnvironmentTier = Literal["dev", "staging", "prod", "unknown"]
DatabaseDialect = Literal["mysql", "postgres", "sqlite", "duckdb", "unknown"]
CatalogStatus = Literal["fresh", "stale", "empty", "unknown"]


class DataEnvironmentProfile(BaseModel):
    """Deterministic snapshot of the datasource environment.

    Produced by EnvironmentService.get_profile().  Safe for Planner,
    PolicyGate, and context injection.  Contains no LLM output.
    """

    datasource_id: str
    project_id: str | None = None

    env: EnvironmentTier = "unknown"
    dialect: DatabaseDialect = "unknown"

    database_name: str | None = None
    default_schema: str | None = None

    catalog_status: CatalogStatus = "unknown"
    catalog_version: str | None = None
    last_synced_at: datetime | None = None

    table_count: int = 0
    selected_tables: list[str] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)


class TableSnapshot(BaseModel):
    """Lightweight table metadata for agent consumption."""

    table_name: str
    table_type: str = "table"
    row_count_estimate: int | None = None
    column_count: int = 0
    columns: list[ColumnSnapshot] = Field(default_factory=list)
    comment: str | None = None
    ai_description: str | None = None
    semantic_tags: list[str] = Field(default_factory=list)
    business_terms: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    table_role: str | None = None
    grain: str | None = None
    subject_area: str | None = None


class ColumnSnapshot(BaseModel):
    """Lightweight column metadata for agent consumption."""

    column_name: str
    data_type: str = ""
    is_nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    column_default: str | None = None
    ai_description: str | None = None
    semantic_tags: list[str] = Field(default_factory=list)
    business_terms: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    column_role: str | None = None
    metric_type: str | None = None


class ForeignKeySnapshot(BaseModel):
    """Foreign key relationship discovered from the live datasource."""

    source_table: str
    column_name: str
    referenced_table: str
    referenced_column: str


class CatalogSnapshot(BaseModel):
    """Snapshot of the DBFox catalog for a datasource.

    Produced by EnvironmentService.get_catalog_snapshot().
    """

    datasource_id: str
    catalog_status: CatalogStatus = "unknown"
    tables: list[TableSnapshot] = Field(default_factory=list)
    relationships: list[ForeignKeySnapshot] = Field(default_factory=list)
    generated_at: datetime | None = None
