"""add domain tag rules table

Revision ID: 2b4c6d8e0f12
Revises: 0a1b2c3d4e5f
Create Date: 2026-06-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2b4c6d8e0f12"
down_revision: Union[str, Sequence[str], None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("domain_tag_rules"):
        return

    op.create_table(
        "domain_tag_rules",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=False),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id",
            "pattern",
            "tag",
            name="uq_domain_tag_rules_ds_pattern_tag",
        ),
    )
    op.create_index(
        "ix_domain_tag_rules_datasource",
        "domain_tag_rules",
        ["data_source_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("domain_tag_rules"):
        return

    op.drop_index("ix_domain_tag_rules_datasource", table_name="domain_tag_rules")
    op.drop_table("domain_tag_rules")
