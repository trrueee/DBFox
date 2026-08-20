"""Add owner_id and package_digest columns to agent_tool_invocations.

Revision ID: c5d6e7f8a9b0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-20
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("agent_tool_invocations") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("package_digest", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_tool_invocations") as batch_op:
        batch_op.drop_column("package_digest")
        batch_op.drop_column("owner_id")
