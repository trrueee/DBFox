"""conversation interaction redesign

Revision ID: f6a7b8c9d0e1
Revises: d1e2f3a4b5c6
Create Date: 2026-06-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("context_tables_json", sa.Text(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))

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

    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_message_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("assistant_message_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("error_code", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("started_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key("fk_agent_runs_user_message", "agent_messages", ["user_message_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_agent_runs_assistant_message", "agent_messages", ["assistant_message_id"], ["id"], ondelete="SET NULL")

    with op.batch_alter_table("agent_artifacts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("message_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("status", sa.String(), nullable=False, server_default="completed"))
        batch_op.create_foreign_key("fk_agent_artifacts_message", "agent_messages", ["message_id"], ["id"], ondelete="SET NULL")

    bind = op.get_bind()
    if sa.inspect(bind).has_table("chat_conversations"):
        op.drop_table("chat_conversations")


def downgrade() -> None:
    with op.batch_alter_table("agent_artifacts", schema=None) as batch_op:
        batch_op.drop_constraint("fk_agent_artifacts_message", type_="foreignkey")
        batch_op.drop_column("status")
        batch_op.drop_column("message_id")

    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_agent_runs_assistant_message", type_="foreignkey")
        batch_op.drop_constraint("fk_agent_runs_user_message", type_="foreignkey")
        batch_op.drop_column("started_at")
        batch_op.drop_column("error_message")
        batch_op.drop_column("error_code")
        batch_op.drop_column("assistant_message_id")
        batch_op.drop_column("user_message_id")

    op.drop_index("ix_agent_messages_role", table_name="agent_messages")
    op.drop_index("ix_agent_messages_session", table_name="agent_messages")
    op.drop_table("agent_messages")

    with op.batch_alter_table("agent_sessions", schema=None) as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("context_tables_json")
