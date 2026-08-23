"""Bind Artifacts to exact Runtime resources.

Revision ID: a8b9c0d1e2f4
Revises: f7a8b9c0d1e3
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a8b9c0d1e2f4"
down_revision: str | None = "f7a8b9c0d1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_artifacts",
        sa.Column(
            "resource_refs_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_artifacts", "resource_refs_json")
