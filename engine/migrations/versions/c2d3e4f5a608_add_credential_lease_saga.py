"""add durable credential lease saga

Revision ID: c2d3e4f5a608
Revises: b1c2d3e4f607
"""

from alembic import op
import sqlalchemy as sa


revision = "c2d3e4f5a608"
down_revision = "b1c2d3e4f607"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credential_leases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("credential_ids_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("committed_at", sa.DateTime(), nullable=True),
        sa.Column("cleanup_started_at", sa.DateTime(), nullable=True),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_credential_leases_status_expires",
        "credential_leases",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_credential_leases_status_expires", table_name="credential_leases")
    op.drop_table("credential_leases")
