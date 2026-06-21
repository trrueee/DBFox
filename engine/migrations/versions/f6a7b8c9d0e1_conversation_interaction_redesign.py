"""conversation interaction redesign

Revision ID: f6a7b8c9d0e1
Revises: f1a2b3c4d5e6
Create Date: 2026-06-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_sessions", sa.Column("context_tables_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("agent_sessions", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("agent_sessions", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="created"),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_agent_messages_session_sequence"),
    )
    op.create_index("ix_agent_messages_session", "agent_messages", ["session_id"])
    op.create_index("ix_agent_messages_role", "agent_messages", ["role"])

    op.add_column("agent_runs", sa.Column("user_message_id", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("assistant_message_id", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("error_code", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.create_foreign_key("fk_agent_runs_user_message", "agent_runs", "agent_messages", ["user_message_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_agent_runs_assistant_message", "agent_runs", "agent_messages", ["assistant_message_id"], ["id"], ondelete="SET NULL")

    op.add_column("agent_artifacts", sa.Column("message_id", sa.String(), nullable=True))
    op.add_column("agent_artifacts", sa.Column("status", sa.String(), nullable=False, server_default="completed"))
    op.create_foreign_key("fk_agent_artifacts_message", "agent_artifacts", "agent_messages", ["message_id"], ["id"], ondelete="SET NULL")

    op.drop_table("chat_conversations")


def downgrade() -> None:
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("context_tables_json", sa.Text(), nullable=False),
        sa.Column("messages_json", sa.Text(), nullable=False),
        sa.Column("artifacts_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_conversations_updated_at", "chat_conversations", ["updated_at"])

    op.drop_constraint("fk_agent_artifacts_message", "agent_artifacts", type_="foreignkey")
    op.drop_column("agent_artifacts", "status")
    op.drop_column("agent_artifacts", "message_id")

    op.drop_constraint("fk_agent_runs_assistant_message", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_user_message", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "started_at")
    op.drop_column("agent_runs", "error_message")
    op.drop_column("agent_runs", "error_code")
    op.drop_column("agent_runs", "assistant_message_id")
    op.drop_column("agent_runs", "user_message_id")

    op.drop_index("ix_agent_messages_role", table_name="agent_messages")
    op.drop_index("ix_agent_messages_session", table_name="agent_messages")
    op.drop_table("agent_messages")

    op.drop_column("agent_sessions", "deleted_at")
    op.drop_column("agent_sessions", "archived_at")
    op.drop_column("agent_sessions", "context_tables_json")
