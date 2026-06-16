"""add_schema_ai_search_metadata

Revision ID: a6b7c8d9e0f1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-16 14:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("schema_tables", schema=None) as batch_op:
        batch_op.add_column(sa.Column("schema_hash", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("ai_description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("semantic_tags", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("business_terms", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("aliases", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("table_role", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("grain", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("subject_area", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("ai_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("ai_enriched_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("schema_columns", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ai_description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("semantic_tags", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("business_terms", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("aliases", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("column_role", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("metric_type", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("is_pii", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("ai_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("ai_enriched_at", sa.DateTime(), nullable=True))

    op.create_table(
        "schema_search_docs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("datasource_id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("table_name", sa.String(), nullable=False),
        sa.Column("column_name", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ai_description", sa.Text(), nullable=True),
        sa.Column("semantic_tags", sa.Text(), nullable=True),
        sa.Column("business_terms", sa.Text(), nullable=True),
        sa.Column("aliases", sa.Text(), nullable=True),
        sa.Column("table_role", sa.String(), nullable=True),
        sa.Column("grain", sa.String(), nullable=True),
        sa.Column("subject_area", sa.String(), nullable=True),
        sa.Column("column_role", sa.String(), nullable=True),
        sa.Column("metric_type", sa.String(), nullable=True),
        sa.Column("column_summary", sa.Text(), nullable=True),
        sa.Column("relation_summary", sa.Text(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["datasource_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schema_search_docs_datasource", "schema_search_docs", ["datasource_id"])
    op.create_index("ix_schema_search_docs_table", "schema_search_docs", ["datasource_id", "table_name"])
    op.create_index("ix_schema_search_docs_entity", "schema_search_docs", ["entity_type", "entity_id"])
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS schema_search_fts
        USING fts5(search_text, content='schema_search_docs', content_rowid='id')
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schema_search_fts")
    op.drop_index("ix_schema_search_docs_entity", table_name="schema_search_docs")
    op.drop_index("ix_schema_search_docs_table", table_name="schema_search_docs")
    op.drop_index("ix_schema_search_docs_datasource", table_name="schema_search_docs")
    op.drop_table("schema_search_docs")

    with op.batch_alter_table("schema_columns", schema=None) as batch_op:
        batch_op.drop_column("ai_enriched_at")
        batch_op.drop_column("ai_confidence")
        batch_op.drop_column("is_pii")
        batch_op.drop_column("metric_type")
        batch_op.drop_column("column_role")
        batch_op.drop_column("aliases")
        batch_op.drop_column("business_terms")
        batch_op.drop_column("semantic_tags")
        batch_op.drop_column("ai_description")

    with op.batch_alter_table("schema_tables", schema=None) as batch_op:
        batch_op.drop_column("ai_enriched_at")
        batch_op.drop_column("ai_confidence")
        batch_op.drop_column("subject_area")
        batch_op.drop_column("grain")
        batch_op.drop_column("table_role")
        batch_op.drop_column("aliases")
        batch_op.drop_column("business_terms")
        batch_op.drop_column("semantic_tags")
        batch_op.drop_column("ai_description")
        batch_op.drop_column("schema_hash")
