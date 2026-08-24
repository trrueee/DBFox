"""Namespace Workspace and GitHub resource identities.

Revision ID: f4a5b6c7d8ea
Revises: f3a4b5c6d7e9

This is a one-time durable rewrite. Runtime aliases and dual-read paths are
intentionally not introduced.
"""

from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8ea"
down_revision: str | None = "f3a4b5c6d7e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND_RENAMES = (
    ("workspace", "dbfox.workspace.root"),
    ("github.repository", "dbfox.github.repository"),
)


def _rewrite_resource_kinds(
    value: object,
    *,
    renames: dict[str, str],
) -> tuple[object, bool]:
    if isinstance(value, list):
        changed = False
        rewritten_items: list[object] = []
        for item in value:
            rewritten, item_changed = _rewrite_resource_kinds(item, renames=renames)
            rewritten_items.append(rewritten)
            changed = changed or item_changed
        return rewritten_items, changed
    if isinstance(value, dict):
        changed = False
        rewritten_fields: dict[str, Any] = {}
        for key, item in value.items():
            if key == "kind" and isinstance(item, str) and item in renames:
                rewritten_fields[key] = renames[item]
                changed = True
                continue
            rewritten, item_changed = _rewrite_resource_kinds(item, renames=renames)
            rewritten_fields[key] = rewritten
            changed = changed or item_changed
        return rewritten_fields, changed
    return value, False


def _rewrite_json_column(*, table: str, column: str, renames: dict[str, str]) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(f"SELECT id, {column} AS payload FROM {table} WHERE {column} IS NOT NULL")
    ).mappings().all()
    for row in rows:
        try:
            parsed = json.loads(str(row["payload"]))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"invalid durable JSON in {table}.{column} for row {row['id']}"
            ) from exc
        rewritten, changed = _rewrite_resource_kinds(parsed, renames=renames)
        if changed:
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


def _rewrite_intents(*, renames: dict[str, str]) -> None:
    connection = op.get_bind()
    for source, target in renames.items():
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


def _rewrite_all(*, renames: dict[str, str]) -> None:
    _rewrite_intents(renames=renames)
    for table, column in (
        ("agent_session_inputs", "resource_refs_json"),
        ("agent_artifacts", "resource_refs_json"),
    ):
        _rewrite_json_column(table=table, column=column, renames=renames)


def upgrade() -> None:
    _rewrite_all(renames=dict(_KIND_RENAMES))


def downgrade() -> None:
    _rewrite_all(renames={target: source for source, target in _KIND_RENAMES})
