"""Add the shadow Memory v4 JSON column.

Revision ID: b5a6c7d8e9f0
Revises: a5f1e2d3c4b6
Create Date: 2026-08-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5a6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "a5f1e2d3c4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_session_memories",
        sa.Column("memory_v4_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_session_memories", "memory_v4_json")
