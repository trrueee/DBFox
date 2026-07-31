"""Add schema identity to catalog search documents.

Revision ID: f0a1b2c3d4e5
Revises: e0f1a2b3c4d5
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f0a1b2c3d4e5"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_schema_search_docs_table", table_name="schema_search_docs")
    op.add_column(
        "schema_search_docs",
        sa.Column(
            "table_schema",
            sa.String(),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index(
        "ix_schema_search_docs_table",
        "schema_search_docs",
        ["datasource_id", "table_schema", "table_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_schema_search_docs_table", table_name="schema_search_docs")
    op.drop_column("schema_search_docs", "table_schema")
    op.create_index(
        "ix_schema_search_docs_table",
        "schema_search_docs",
        ["datasource_id", "table_name"],
    )
