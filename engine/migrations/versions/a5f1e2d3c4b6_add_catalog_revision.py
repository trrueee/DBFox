"""Add the search-visible catalog publication revision.

Revision ID: a5f1e2d3c4b6
Revises: 14cd56ef78a1
Create Date: 2026-08-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5f1e2d3c4b6"
down_revision: Union[str, Sequence[str], None] = "14cd56ef78a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "data_sources",
        sa.Column(
            "catalog_revision",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("data_sources", "catalog_revision")
