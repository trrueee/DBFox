"""add datasource health snapshot

Revision ID: f1a2b3c4d5e6
Revises: a3d7346c7b53
Create Date: 2026-05-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "a3d7346c7b53"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add persisted health-check snapshot fields to saved datasources."""
    with op.batch_alter_table("data_sources", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_test_latency_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_test_readonly", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("last_test_server_version", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("last_test_tables_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_test_warnings", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove datasource health-check snapshot fields."""
    with op.batch_alter_table("data_sources", schema=None) as batch_op:
        batch_op.drop_column("last_test_warnings")
        batch_op.drop_column("last_test_tables_count")
        batch_op.drop_column("last_test_server_version")
        batch_op.drop_column("last_test_readonly")
        batch_op.drop_column("last_test_latency_ms")
