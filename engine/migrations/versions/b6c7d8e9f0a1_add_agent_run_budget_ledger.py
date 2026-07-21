"""add agent run budget ledger

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-07-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("consumed_input_tokens", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("consumed_output_tokens", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("consumed_tokens", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("consumed_cost_usd", sa.Float(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("provider_retry_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("repair_attempt_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_column("repair_attempt_count")
        batch_op.drop_column("provider_retry_count")
        batch_op.drop_column("consumed_cost_usd")
        batch_op.drop_column("consumed_tokens")
        batch_op.drop_column("consumed_output_tokens")
        batch_op.drop_column("consumed_input_tokens")
