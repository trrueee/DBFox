"""Test-only helpers — not imported by production code."""

from verification.support.metadata import (
    create_migrated_metadata_engine,
    sqlite_metadata_url,
)

__all__ = [
    "create_migrated_metadata_engine",
    "sqlite_metadata_url",
]
