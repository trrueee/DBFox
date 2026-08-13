"""Use FTS5 trigram tokenization for query-history substring search.

Revision ID: 14cd56ef78a1
Revises: 13bc45de67f0
Create Date: 2026-08-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "14cd56ef78a1"
down_revision: Union[str, Sequence[str], None] = "13bc45de67f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TRIGGERS = (
    """
    CREATE TRIGGER query_history_search_docs_ai
    AFTER INSERT ON query_history_search_docs BEGIN
        INSERT INTO query_history_fts(rowid, search_text)
        VALUES (new.id, new.search_text);
    END
    """,
    """
    CREATE TRIGGER query_history_search_docs_ad
    AFTER DELETE ON query_history_search_docs BEGIN
        INSERT INTO query_history_fts(query_history_fts, rowid, search_text)
        VALUES ('delete', old.id, old.search_text);
    END
    """,
    """
    CREATE TRIGGER query_history_search_docs_au
    AFTER UPDATE ON query_history_search_docs BEGIN
        INSERT INTO query_history_fts(query_history_fts, rowid, search_text)
        VALUES ('delete', old.id, old.search_text);
        INSERT INTO query_history_fts(rowid, search_text)
        VALUES (new.id, new.search_text);
    END
    """,
)


def _replace_query_history_fts(*, tokenizer: str | None) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    for trigger_name in (
        "query_history_search_docs_au",
        "query_history_search_docs_ad",
        "query_history_search_docs_ai",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
    op.execute("DROP TABLE IF EXISTS query_history_fts")
    tokenizer_clause = f", tokenize='{tokenizer}'" if tokenizer else ""
    op.execute(
        "CREATE VIRTUAL TABLE query_history_fts "
        "USING fts5(search_text, content='query_history_search_docs', "
        f"content_rowid='id'{tokenizer_clause})"
    )
    for trigger in _TRIGGERS:
        op.execute(trigger)
    op.execute("INSERT INTO query_history_fts(query_history_fts) VALUES ('rebuild')")


def upgrade() -> None:
    _replace_query_history_fts(tokenizer="trigram")


def downgrade() -> None:
    _replace_query_history_fts(tokenizer=None)
