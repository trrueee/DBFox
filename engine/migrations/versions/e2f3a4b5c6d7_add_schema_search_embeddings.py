"""add schema search embeddings

Revision ID: e2f3a4b5c6d7
Revises: 0a1b2c3d4e5f
Create Date: 2026-06-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schema_search_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("datasource_id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("embedding_model", sa.String(), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("search_text_hash", sa.String(), nullable=False),
        sa.Column("embedding_blob", sa.LargeBinary(), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["datasource_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "datasource_id",
            "entity_type",
            "entity_id",
            "embedding_model",
            "embedding_dimension",
            name="uq_schema_search_embeddings_doc_model_dim",
        ),
    )
    op.create_index(
        "ix_schema_search_embeddings_datasource",
        "schema_search_embeddings",
        ["datasource_id"],
    )
    op.create_index(
        "ix_schema_search_embeddings_lookup",
        "schema_search_embeddings",
        ["datasource_id", "embedding_model", "embedding_dimension"],
    )


def downgrade() -> None:
    op.drop_index("ix_schema_search_embeddings_lookup", table_name="schema_search_embeddings")
    op.drop_index("ix_schema_search_embeddings_datasource", table_name="schema_search_embeddings")
    op.drop_table("schema_search_embeddings")
