"""Namespace the Data database resource identity.

Revision ID: d1e2f3a4b5c7
Revises: c0d1e2f3a4ba

The Runtime has one resource protocol.  This migration rewrites the retired
bare ``database`` kind at the durable boundary so production code does not
need a runtime alias, mapper, or dual-read path.
"""

from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c7"
down_revision: str | None = "c0d1e2f3a4ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_KIND = "database"
_NEW_KIND = "dbfox.data.database"


def _rewrite_resource_kind(value: object, *, source: str, target: str) -> tuple[object, bool]:
    if isinstance(value, list):
        changed = False
        rewritten_items: list[object] = []
        for item in value:
            next_item, item_changed = _rewrite_resource_kind(
                item,
                source=source,
                target=target,
            )
            rewritten_items.append(next_item)
            changed = changed or item_changed
        return rewritten_items, changed

    if isinstance(value, dict):
        changed = False
        rewritten_fields: dict[str, Any] = {}
        for key, item in value.items():
            if key == "kind" and item == source:
                rewritten_fields[key] = target
                changed = True
                continue
            next_item, item_changed = _rewrite_resource_kind(
                item,
                source=source,
                target=target,
            )
            rewritten_fields[key] = next_item
            changed = changed or item_changed
        return rewritten_fields, changed

    return value, False


def _rewrite_json_column(
    *,
    table: str,
    column: str,
    source: str,
    target: str,
) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(f"SELECT id, {column} AS payload FROM {table} WHERE {column} IS NOT NULL")
    ).mappings().all()
    for row in rows:
        try:
            parsed = json.loads(str(row["payload"]))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"invalid durable JSON in {table}.{column} for row {row['id']}") from exc
        rewritten, changed = _rewrite_resource_kind(
            parsed,
            source=source,
            target=target,
        )
        if not changed:
            continue
        connection.execute(
            sa.text(f"UPDATE {table} SET {column} = :payload WHERE id = :row_id"),
            {
                "payload": json.dumps(
                    rewritten,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "row_id": row["id"],
            },
        )


def _rewrite_intents(*, source: str, target: str) -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM conversation_resource_intents "
            "WHERE kind = :source AND EXISTS ("
            "SELECT 1 FROM conversation_resource_intents AS existing "
            "WHERE existing.conversation_id = conversation_resource_intents.conversation_id "
            "AND existing.kind = :target "
            "AND existing.resource_id = conversation_resource_intents.resource_id"
            ")"
        ),
        {"source": source, "target": target},
    )
    connection.execute(
        sa.text(
            "UPDATE conversation_resource_intents SET kind = :target WHERE kind = :source"
        ),
        {"source": source, "target": target},
    )


def _rewrite_all(*, source: str, target: str) -> None:
    _rewrite_intents(source=source, target=target)
    _rewrite_json_column(
        table="agent_session_inputs",
        column="resource_refs_json",
        source=source,
        target=target,
    )
    _rewrite_json_column(
        table="agent_artifacts",
        column="resource_refs_json",
        source=source,
        target=target,
    )
    _rewrite_json_column(
        table="agent_session_memories",
        column="memory_v4_json",
        source=source,
        target=target,
    )


def upgrade() -> None:
    _rewrite_all(source=_OLD_KIND, target=_NEW_KIND)


def downgrade() -> None:
    _rewrite_all(source=_NEW_KIND, target=_OLD_KIND)
