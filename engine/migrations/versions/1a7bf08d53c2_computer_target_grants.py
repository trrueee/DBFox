"""Add Host computer target authorization; execution and artifacts stay canonical.

Revision ID: 1a7bf08d53c2
Revises: 0f6ae97c42b1
"""
from alembic import op
import sqlalchemy as sa

revision = "1a7bf08d53c2"
down_revision = "0f6ae97c42b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "computer_grants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("engine_generation", sa.String(), nullable=False),
        sa.Column("target_kind", sa.String(), nullable=False),
        sa.Column("target_json", sa.Text(), nullable=False),
        sa.Column("permission", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("permission IN ('observe', 'control')", name="ck_computer_grant_permission"),
        sa.CheckConstraint("status IN ('active', 'paused', 'revoked', 'interrupted')", name="ck_computer_grant_status"),
    )
    op.create_index("ix_computer_grants_session_created", "computer_grants", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_computer_grants_session_created", table_name="computer_grants")
    op.drop_table("computer_grants")
