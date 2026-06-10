"""Single source of truth for database dialect resolution."""
from __future__ import annotations

from sqlalchemy.orm import Session

from engine.environment.datasource_resolver import resolve_datasource


def resolve_datasource_dialect(db: Session, datasource_id: str) -> str:
    """Return the canonical dialect string for *datasource_id*.

    This is the ONE place that determines dialect.  All other code
    (ExecutionContext, SQL generation, validation, introspection)
    should call this function rather than guessing or hardcoding.
    """
    try:
        resolved = resolve_datasource(db, datasource_id)
        return resolved.dialect
    except ValueError:
        return "mysql"
