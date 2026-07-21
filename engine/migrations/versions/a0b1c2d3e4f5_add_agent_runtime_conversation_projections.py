"""persist v2 conversation messages and artifacts with runtime runs

Revision ID: a0b1c2d3e4f5
Revises: 9e0f1a2b3c4d
Create Date: 2026-07-12

The durable Agent runtime owns the conversation projection used by the UI.
Each v2 run creates exactly one user and one assistant message in the same
transaction as its run row and initial outbox record.  Artifacts are then
projected transactionally from committed outbox/terminal payloads.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "9e0f1a2b3c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column("runtime_message_sequence", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "agent_runtime_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="created"),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_agent_runtime_messages_role"),
        sa.CheckConstraint(
            "status IN ('created', 'streaming', 'completed', 'failed', 'cancelled')",
            name="ck_agent_runtime_messages_status",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runtime_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_agent_runtime_messages_conversation_sequence",
        ),
        sa.UniqueConstraint("run_id", "role", name="uq_agent_runtime_messages_run_role"),
    )
    op.create_index(
        "ix_agent_runtime_messages_conversation",
        "agent_runtime_messages",
        ["conversation_id", "sequence"],
    )
    op.create_index("ix_agent_runtime_messages_run", "agent_runtime_messages", ["run_id"])

    op.create_table(
        "agent_runtime_artifacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("semantic_id", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("presentation_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("depends_on_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("refs_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="completed"),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runtime_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["agent_runtime_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runtime_artifacts_run", "agent_runtime_artifacts", ["run_id", "sequence"])
    op.create_index(
        "ix_agent_runtime_artifacts_conversation",
        "agent_runtime_artifacts",
        ["conversation_id"],
    )
    op.create_index("ix_agent_runtime_artifacts_message", "agent_runtime_artifacts", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runtime_artifacts_message", table_name="agent_runtime_artifacts")
    op.drop_index("ix_agent_runtime_artifacts_conversation", table_name="agent_runtime_artifacts")
    op.drop_index("ix_agent_runtime_artifacts_run", table_name="agent_runtime_artifacts")
    op.drop_table("agent_runtime_artifacts")
    op.drop_index("ix_agent_runtime_messages_run", table_name="agent_runtime_messages")
    op.drop_index("ix_agent_runtime_messages_conversation", table_name="agent_runtime_messages")
    op.drop_table("agent_runtime_messages")
    op.drop_column("agent_sessions", "runtime_message_sequence")
