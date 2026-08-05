"""Add the derived FTS5 index for current-session conversation recall.

Revision ID: 13bc45de67f0
Revises: 12ab34cd56ef
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "13bc45de67f0"
down_revision: Union[str, Sequence[str], None] = "12ab34cd56ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_message_search_docs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.String(), nullable=False, unique=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["agent_messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["agent_sessions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_agent_message_search_docs_session_sequence",
        "agent_message_search_docs",
        ["session_id", "sequence"],
    )
    op.execute(
        """
        CREATE VIRTUAL TABLE agent_message_fts
        USING fts5(
            search_text,
            content='agent_message_search_docs',
            content_rowid='id',
            tokenize='trigram'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER agent_message_search_docs_ai
        AFTER INSERT ON agent_message_search_docs BEGIN
            INSERT INTO agent_message_fts(rowid, search_text)
            VALUES (new.id, new.search_text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER agent_message_search_docs_ad
        AFTER DELETE ON agent_message_search_docs BEGIN
            INSERT INTO agent_message_fts(agent_message_fts, rowid, search_text)
            VALUES ('delete', old.id, old.search_text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER agent_message_search_docs_au
        AFTER UPDATE ON agent_message_search_docs BEGIN
            INSERT INTO agent_message_fts(agent_message_fts, rowid, search_text)
            VALUES ('delete', old.id, old.search_text);
            INSERT INTO agent_message_fts(rowid, search_text)
            VALUES (new.id, new.search_text);
        END
        """
    )

    # The canonical transcript owns message lifecycle.  These triggers keep the
    # projection transactionally current without adding a second write path.
    op.execute(
        """
        CREATE TRIGGER agent_messages_recall_ai
        AFTER INSERT ON agent_messages
        WHEN new.role = 'user' OR (new.role = 'assistant' AND new.status = 'completed')
        BEGIN
            INSERT INTO agent_message_search_docs (
                message_id, session_id, sequence, role, status,
                search_text, created_at, updated_at
            ) VALUES (
                new.id, new.session_id, new.sequence, new.role, new.status,
                new.content, new.created_at, CURRENT_TIMESTAMP
            );
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER agent_messages_recall_ad
        AFTER DELETE ON agent_messages BEGIN
            DELETE FROM agent_message_search_docs WHERE message_id = old.id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER agent_messages_recall_au
        AFTER UPDATE OF session_id, sequence, role, status, content, created_at ON agent_messages
        BEGIN
            DELETE FROM agent_message_search_docs WHERE message_id = old.id;
            INSERT INTO agent_message_search_docs (
                message_id, session_id, sequence, role, status,
                search_text, created_at, updated_at
            )
            SELECT
                new.id, new.session_id, new.sequence, new.role, new.status,
                new.content, new.created_at, CURRENT_TIMESTAMP
            WHERE new.role = 'user'
               OR (new.role = 'assistant' AND new.status = 'completed');
        END
        """
    )

    op.execute(
        """
        INSERT INTO agent_message_search_docs (
            message_id, session_id, sequence, role, status,
            search_text, created_at, updated_at
        )
        SELECT
            id, session_id, sequence, role, status,
            content, created_at, CURRENT_TIMESTAMP
        FROM agent_messages
        WHERE role = 'user' OR (role = 'assistant' AND status = 'completed')
        """
    )
    op.execute("INSERT INTO agent_message_fts(agent_message_fts) VALUES ('rebuild')")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS agent_messages_recall_au")
    op.execute("DROP TRIGGER IF EXISTS agent_messages_recall_ad")
    op.execute("DROP TRIGGER IF EXISTS agent_messages_recall_ai")
    op.execute("DROP TRIGGER IF EXISTS agent_message_search_docs_au")
    op.execute("DROP TRIGGER IF EXISTS agent_message_search_docs_ad")
    op.execute("DROP TRIGGER IF EXISTS agent_message_search_docs_ai")
    op.execute("DROP TABLE IF EXISTS agent_message_fts")
    op.drop_index(
        "ix_agent_message_search_docs_session_sequence",
        table_name="agent_message_search_docs",
    )
    op.drop_table("agent_message_search_docs")
