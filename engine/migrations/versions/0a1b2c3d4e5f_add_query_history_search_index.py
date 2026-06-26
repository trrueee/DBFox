"""add query history search index content table

Revision ID: 0a1b2c3d4e5f
Revises: f7a8b9c0d1e2
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS query_history_fts")
    op.execute("DROP TABLE IF EXISTS query_history_search_docs")
    op.create_table(
        "query_history_search_docs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("history_id", sa.String(), nullable=False, unique=True),
        sa.Column("datasource_id", sa.String(), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("submitted_sql", sa.Text(), nullable=True),
        sa.Column("generated_sql", sa.Text(), nullable=True),
        sa.Column("safe_sql", sa.Text(), nullable=True),
        sa.Column("executed_sql", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["history_id"], ["query_history.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_query_history_search_docs_datasource",
        "query_history_search_docs",
        ["datasource_id"],
    )
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS query_history_fts
        USING fts5(search_text, content='query_history_search_docs', content_rowid='id')
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS query_history_search_docs_ai
        AFTER INSERT ON query_history_search_docs BEGIN
            INSERT INTO query_history_fts(rowid, search_text)
            VALUES (new.id, new.search_text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS query_history_search_docs_ad
        AFTER DELETE ON query_history_search_docs BEGIN
            INSERT INTO query_history_fts(query_history_fts, rowid, search_text)
            VALUES ('delete', old.id, old.search_text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS query_history_search_docs_au
        AFTER UPDATE ON query_history_search_docs BEGIN
            INSERT INTO query_history_fts(query_history_fts, rowid, search_text)
            VALUES ('delete', old.id, old.search_text);
            INSERT INTO query_history_fts(rowid, search_text)
            VALUES (new.id, new.search_text);
        END
        """
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO query_history_search_docs (
                history_id, datasource_id, question, submitted_sql, generated_sql,
                safe_sql, executed_sql, error_message, search_text, created_at, updated_at
            )
            SELECT
                id,
                data_source_id,
                question,
                submitted_sql,
                generated_sql,
                safe_sql,
                executed_sql,
                error_message,
                trim(
                    coalesce(question, '') || ' ' ||
                    coalesce(submitted_sql, '') || ' ' ||
                    coalesce(generated_sql, '') || ' ' ||
                    coalesce(safe_sql, '') || ' ' ||
                    coalesce(executed_sql, '') || ' ' ||
                    coalesce(error_message, '')
                ),
                created_at,
                CURRENT_TIMESTAMP
            FROM query_history
            """
        )
    )
    op.execute("INSERT INTO query_history_fts(query_history_fts) VALUES ('rebuild')")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS query_history_search_docs_au")
    op.execute("DROP TRIGGER IF EXISTS query_history_search_docs_ad")
    op.execute("DROP TRIGGER IF EXISTS query_history_search_docs_ai")
    op.execute("DROP TABLE IF EXISTS query_history_fts")
    op.drop_index("ix_query_history_search_docs_datasource", table_name="query_history_search_docs")
    op.drop_table("query_history_search_docs")
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS query_history_fts
        USING fts5(
            history_id UNINDEXED,
            question,
            submitted_sql,
            generated_sql,
            safe_sql,
            executed_sql,
            error_message
        )
        """
    )
