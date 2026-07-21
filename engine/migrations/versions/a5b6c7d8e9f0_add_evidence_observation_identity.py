"""add evidence observation identity

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-07-19
"""
from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("agent_evidence") as batch_op:
        batch_op.add_column(sa.Column("query_fingerprint", sa.String(), nullable=False, server_default=""))
        batch_op.add_column(
            sa.Column("observed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))
        )

    connection = op.get_bind()
    rows = connection.execute(sa.text(
        'SELECT e.id, a.payload_json, a.created_at '
        'FROM agent_evidence e JOIN agent_artifacts a ON a.id = e.artifact_id'
    )).fetchall()
    update = sa.text(
        'UPDATE agent_evidence SET query_fingerprint = :fingerprint, observed_at = :observed_at WHERE id = :id'
    )
    for evidence_id, raw_payload, created_at in rows:
        try:
            payload = json.loads(raw_payload or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        connection.execute(update, {
            "id": evidence_id,
            "fingerprint": str(payload.get("queryFingerprint") or ""),
            "observed_at": payload.get("executedAt") or created_at,
        })


def downgrade() -> None:
    with op.batch_alter_table("agent_evidence") as batch_op:
        batch_op.drop_column("observed_at")
        batch_op.drop_column("query_fingerprint")
