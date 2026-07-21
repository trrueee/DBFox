"""add durable isolated restore operations

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-07-13
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "restore_operations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("backup_id", sa.String(), nullable=False),
        sa.Column("datasource_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_database_name", sa.String(), nullable=False),
        sa.Column("target_database_name", sa.String(), nullable=False),
        sa.Column("expected_generation", sa.Integer(), nullable=False),
        sa.Column("committed_generation", sa.Integer(), nullable=True),
        sa.Column("validated_table_count", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["backup_id"], ["backup_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["datasource_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_restore_operations_backup", "restore_operations", ["backup_id"])
    op.create_index("ix_restore_operations_datasource", "restore_operations", ["datasource_id"])
    op.create_index("ix_restore_operations_created", "restore_operations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_restore_operations_created", table_name="restore_operations")
    op.drop_index("ix_restore_operations_datasource", table_name="restore_operations")
    op.drop_index("ix_restore_operations_backup", table_name="restore_operations")
    op.drop_table("restore_operations")
