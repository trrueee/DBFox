"""repair the Alembic-owned metadata FTS contract

Revision ID: 6b7c8d9e0f1a
Revises: 5a6b7c8d9e0f
Create Date: 2026-07-11

Older startup code could call ``Base.metadata.create_all()`` and then stamp
head, leaving FTS virtual tables/triggers absent even though Alembic recorded a
current revision.  This migration is an intentional one-time repair: all FTS
DDL now belongs exclusively to migrations and runtime code only asserts it.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6b7c8d9e0f1a"
down_revision: Union[str, Sequence[str], None] = "5a6b7c8d9e0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCHEMA_FTS_DDL = """
CREATE VIRTUAL TABLE schema_search_fts
USING fts5(search_text, content='schema_search_docs', content_rowid='id')
"""

_QUERY_FTS_DDL = """
CREATE VIRTUAL TABLE query_history_fts
USING fts5(search_text, content='query_history_search_docs', content_rowid='id')
"""

_QUERY_FTS_TRIGGERS = (
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


def _repair_fts_contract() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    op.execute("DROP TRIGGER IF EXISTS query_history_search_docs_au")
    op.execute("DROP TRIGGER IF EXISTS query_history_search_docs_ad")
    op.execute("DROP TRIGGER IF EXISTS query_history_search_docs_ai")
    op.execute("DROP TABLE IF EXISTS query_history_fts")
    op.execute("DROP TABLE IF EXISTS schema_search_fts")

    op.execute(sa.text(_SCHEMA_FTS_DDL))
    op.execute(sa.text(_QUERY_FTS_DDL))
    for trigger in _QUERY_FTS_TRIGGERS:
        op.execute(sa.text(trigger))
    op.execute("INSERT INTO schema_search_fts(schema_search_fts) VALUES ('rebuild')")
    op.execute("INSERT INTO query_history_fts(query_history_fts) VALUES ('rebuild')")


def upgrade() -> None:
    _repair_fts_contract()


def downgrade() -> None:
    # The prior revision expects the same virtual-table shape.  Keeping the
    # repaired contract is safer than reintroducing a runtime-DLL divergence.
    _repair_fts_contract()
