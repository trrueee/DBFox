"""Freeze the exact function output supplied to the model.

Revision ID: 0a1b2c3d4e6f
Revises: f0a1b2c3d4e5
"""

from __future__ import annotations

import json
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "0a1b2c3d4e6f"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def _load(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def upgrade() -> None:
    op.add_column(
        "agent_observations",
        sa.Column("model_output_json", sa.Text(), nullable=True),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, status, model_visible_summary, facts_json, "
            "artifact_ids_json, retryable, error_code, error_message "
            "FROM agent_observations"
        )
    ).mappings()
    for row in rows:
        value = {
            "status": str(row["status"]),
            "summary": str(row["model_visible_summary"] or ""),
            "facts": _load(row["facts_json"], {}),
            "artifact_ids": _load(row["artifact_ids_json"], []),
            "retryable": bool(row["retryable"]),
        }
        if row["error_code"]:
            value["error_code"] = str(row["error_code"])
        if row["error_message"]:
            value["error_message"] = str(row["error_message"])
        bind.execute(
            sa.text(
                "UPDATE agent_observations "
                "SET model_output_json = :model_output WHERE id = :id"
            ),
            {"id": row["id"], "model_output": _canonical(value)},
        )
    with op.batch_alter_table("agent_observations") as batch_op:
        batch_op.alter_column(
            "model_output_json",
            existing_type=sa.Text(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_observations") as batch_op:
        batch_op.drop_column("model_output_json")
