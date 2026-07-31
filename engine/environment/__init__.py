"""Data Environment Layer — turns a real database into an agent-understandable environment.

Modules:
  catalog_introspector — reflect live database catalogs through one service
  schema_catalog_sync  — sync introspection results to SchemaTable / SchemaColumn
  inventory            — typed data models for introspection results
  er_diagram           — deterministic ER diagram rendering
  authoritative_inventory — authoritative schema metadata model
"""
