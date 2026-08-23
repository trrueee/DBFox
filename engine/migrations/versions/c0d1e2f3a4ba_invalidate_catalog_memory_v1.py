"""Invalidate the retired datasource-shaped Catalog Memory projection.

Revision ID: c0d1e2f3a4ba
Revises: c0d1e2f3a4b9

Memory v4 is a rebuildable projection, not canonical state.  Extension API v2
uses the same frozen ResourceScopeRef envelope throughout the Runtime, so the
old Catalog scope containing datasource_id/datasource_generation must not stay
readable.  Preserve Core and unrelated DLC projections and remove only the
retired dbfox.data Catalog projection; the next projection pass rebuilds it
from canonical Runs and Observations.
"""

from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any

from alembic import op
import sqlalchemy as sa


revision: str = "c0d1e2f3a4ba"
down_revision: str | None = "c0d1e2f3a4b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATALOG_PROJECTION_ID = "dbfox.catalog.working_state"


def _without_retired_catalog_projection(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    raw_projections = value.get("projections")
    if not isinstance(raw_projections, list):
        return None
    projections = [
        item
        for item in raw_projections
        if not (
            isinstance(item, dict)
            and item.get("extension_id") == "dbfox.data"
            and item.get("projection_id") == _CATALOG_PROJECTION_ID
        )
    ]
    if len(projections) == len(raw_projections):
        return None
    updated = dict(value)
    updated["projections"] = projections
    return updated


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, memory_v4_json FROM agent_session_memories "
            "WHERE memory_v4_json IS NOT NULL"
        )
    ).mappings()
    for row in rows:
        try:
            parsed = json.loads(str(row["memory_v4_json"]))
        except (TypeError, ValueError):
            continue
        updated = _without_retired_catalog_projection(parsed)
        if updated is None:
            continue
        encoded = json.dumps(
            updated,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        connection.execute(
            sa.text(
                "UPDATE agent_session_memories "
                "SET memory_v4_json = :payload WHERE id = :memory_id"
            ),
            {"payload": encoded, "memory_id": row["id"]},
        )


def downgrade() -> None:
    # Derived projection bytes cannot be reconstructed during downgrade.  The
    # v1 Runtime will rebuild from canonical Runs and Observations as needed.
    pass
