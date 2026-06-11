"""add_chat_conversations_table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("context_tables_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("messages_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("artifacts_json", sa.Text(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_conversations_updated_at", "chat_conversations", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_conversations_updated_at", table_name="chat_conversations")
    op.drop_table("chat_conversations")
