"""Retire the removed table-design draft storage.

Revision ID: d3e4f5a6b709
Revises: c2d3e4f5a608
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "d3e4f5a6b709"
down_revision: str | None = "c2d3e4f5a608"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_table_design_drafts_project", table_name="table_design_drafts")
    op.drop_table("table_design_drafts")


def downgrade() -> None:
    op.create_table(
        "table_design_drafts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("table_name", sa.String(), nullable=False),
        sa.Column("table_comment", sa.String(), nullable=True),
        sa.Column("columns_json", sa.Text(), nullable=False),
        sa.Column("indexes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_table_design_drafts_project",
        "table_design_drafts",
        ["project_id"],
        unique=False,
    )
