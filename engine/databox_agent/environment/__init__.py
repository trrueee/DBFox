"""Data Environment Layer — turns a real database into an agent-understandable environment.

Modules:
  datasource_resolver  — resolve datasource config into a uniform model
  dialect_resolver     — single source of truth for dialect
  schema_introspector  — introspect real databases (SQLite, MySQL, …)
  schema_catalog_sync  — sync introspection results to SchemaTable / SchemaColumn
  schema_inventory     — typed data models for introspection results
  connection_factory   — unified connection creation per dialect
  models               — DataEnvironmentProfile, CatalogSnapshot, TableSnapshot
  service              — EnvironmentService — unified environment fact query API
  tools                — environment-aware tools registered into the agent registry
"""

from engine.databox_agent.environment.models import (
    CatalogSnapshot,
    ColumnSnapshot,
    DataEnvironmentProfile,
    ForeignKeySnapshot,
    TableSnapshot,
)
from engine.databox_agent.environment.service import EnvironmentService

__all__ = [
    "CatalogSnapshot",
    "ColumnSnapshot",
    "DataEnvironmentProfile",
    "EnvironmentService",
    "ForeignKeySnapshot",
    "TableSnapshot",
]
