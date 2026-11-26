"""Track process-interruption recovery separately from provider retries.

Revision ID: 2c9d0e1f4a55
Revises: 1a7bf08d53c2
"""
from alembic import op
import sqlalchemy as sa


revision = "2c9d0e1f4a55"
down_revision = "1a7bf08d53c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "recovery_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "recovery_count")
