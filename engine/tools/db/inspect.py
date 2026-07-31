"""Live catalog object inspection through the authoritative reflection service."""
from __future__ import annotations

from sqlalchemy.orm import Session

from engine.connectivity.factory import ConnectionFactory
from engine.environment.catalog_introspector import CatalogIntrospector
from engine.environment.inventory import InspectedColumnObject, InspectedTable


def db_inspect(
    db: Session,
    datasource_id: str,
    targets: list[str],
    *,
    connection_factory: ConnectionFactory | None = None,
) -> list[InspectedTable | InspectedColumnObject]:
    """Inspect one bounded target set with one managed live connection."""

    return CatalogIntrospector(
        connection_factory=connection_factory,
    ).inspect_objects(
        db,
        datasource_id,
        targets,
    )
