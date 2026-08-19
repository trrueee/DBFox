"""Add github_repository_bindings table.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_repository_bindings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("repository", sa.String(), nullable=False),
        sa.Column("ref_name", sa.String(), nullable=False, server_default="main"),
        sa.Column("resolved_revision", sa.String(), nullable=False),
        sa.Column("default_branch", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "project_id",
            "owner",
            "repository",
            "ref_name",
            name="uq_github_repository_bindings_project_repo_ref",
        ),
    )
    op.create_index(
        "ix_github_repository_bindings_project",
        "github_repository_bindings",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_github_repository_bindings_project",
        table_name="github_repository_bindings",
    )
    op.drop_table("github_repository_bindings")
