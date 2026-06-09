"""Data Environment Layer — turns a real database into an agent-understandable environment.

Modules:
  datasource_resolver  — resolve datasource config into a uniform model
  dialect_resolver     — single source of truth for dialect
  schema_introspector  — introspect real databases (SQLite, MySQL, …)
  schema_catalog_sync  — sync introspection results to SchemaTable / SchemaColumn
  schema_inventory     — typed data models for the environment layer
  connection_factory   — unified connection creation per dialect
"""
