"""Remove legacy Agent memory summary columns.

Revision ID: b1c2d3e4f607
Revises: 0a1b2c3d4e6f
"""

from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f607"
down_revision = "0a1b2c3d4e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_session_memories") as batch:
        batch.drop_column("summary_cursor_message_id")
        batch.drop_column("conversation_summary")


def downgrade() -> None:
    with op.batch_alter_table("agent_session_memories") as batch:
        batch.add_column(sa.Column("conversation_summary", sa.Text(), nullable=True))
        batch.add_column(sa.Column("summary_cursor_message_id", sa.String(), nullable=True))
