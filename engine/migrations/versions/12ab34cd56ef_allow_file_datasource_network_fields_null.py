"""Allow file-backed datasources to omit network-only coordinates.

Revision ID: 12ab34cd56ef
Revises: f8b9c0d1e2f3
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "12ab34cd56ef"
down_revision = "f8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.alter_column(
            "host",
            existing_type=sa.String(),
            nullable=True,
        )
        batch_op.alter_column(
            "port",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.alter_column(
            "username",
            existing_type=sa.String(),
            nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE data_sources SET host = '' WHERE host IS NULL"))
    bind.execute(sa.text("UPDATE data_sources SET port = 0 WHERE port IS NULL"))
    bind.execute(sa.text("UPDATE data_sources SET username = '' WHERE username IS NULL"))
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.alter_column(
            "host",
            existing_type=sa.String(),
            nullable=False,
        )
        batch_op.alter_column(
            "port",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "username",
            existing_type=sa.String(),
            nullable=False,
        )
