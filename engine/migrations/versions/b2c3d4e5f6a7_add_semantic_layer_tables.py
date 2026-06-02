"""add semantic layer tables

Revision ID: b2c3d4e5f6a7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create semantic aliases, metrics, dimensions, and workspace table scope tables."""
    op.create_table(
        "semantic_aliases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=False),
        sa.Column("alias", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "alias", "target_type", "target", name="uq_semantic_aliases_ds_alias_target"),
    )
    op.create_index("ix_semantic_aliases_datasource", "semantic_aliases", ["data_source_id"])
    op.create_index("ix_semantic_aliases_alias", "semantic_aliases", ["alias"])

    op.create_table(
        "semantic_metrics",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("expression", sa.String(), nullable=False),
        sa.Column("source_columns_json", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "name", name="uq_semantic_metrics_ds_name"),
    )
    op.create_index("ix_semantic_metrics_datasource", "semantic_metrics", ["data_source_id"])

    op.create_table(
        "semantic_dimensions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("column_ref", sa.String(), nullable=False),
        sa.Column("transform", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "name", name="uq_semantic_dimensions_ds_name"),
    )
    op.create_index("ix_semantic_dimensions_datasource", "semantic_dimensions", ["data_source_id"])

    op.create_table(
        "workspace_table_scopes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=False),
        sa.Column("table_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "data_source_id", "table_id", name="uq_workspace_scopes_project_ds_table"),
    )
    op.create_index("ix_workspace_table_scopes_project_ds", "workspace_table_scopes", ["project_id", "data_source_id"])


def downgrade() -> None:
    """Drop semantic layer tables."""
    op.drop_index("ix_workspace_table_scopes_project_ds", table_name="workspace_table_scopes")
    op.drop_table("workspace_table_scopes")
    op.drop_index("ix_semantic_dimensions_datasource", table_name="semantic_dimensions")
    op.drop_table("semantic_dimensions")
    op.drop_index("ix_semantic_metrics_datasource", table_name="semantic_metrics")
    op.drop_table("semantic_metrics")
    op.drop_index("ix_semantic_aliases_alias", table_name="semantic_aliases")
    op.drop_index("ix_semantic_aliases_datasource", table_name="semantic_aliases")
    op.drop_table("semantic_aliases")
