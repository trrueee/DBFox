"""converge Agent Turn completion onto canonical termination and RunItems

Revision ID: f8b9c0d1e2f3
Revises: e4f5a6b7c810
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f8b9c0d1e2f3"
down_revision: str | None = "e4f5a6b7c810"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_turns") as batch_op:
        batch_op.add_column(sa.Column("termination", sa.String(), nullable=True))

    # Preserve only values that belong to the new provider-neutral enum.  Legacy
    # provider finish strings never represented a trustworthy completion state.
    op.execute(
        sa.text(
            """
            UPDATE agent_turns
            SET termination = finish_signal
            WHERE finish_signal IN ('completed', 'incomplete', 'failed', 'cancelled')
            """
        )
    )

    with op.batch_alter_table("agent_turns") as batch_op:
        batch_op.drop_column("draft_text")
        batch_op.drop_column("message_phase")
        batch_op.drop_column("finish_signal")


def downgrade() -> None:
    with op.batch_alter_table("agent_turns") as batch_op:
        batch_op.add_column(
            sa.Column("draft_text", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("message_phase", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("finish_signal", sa.String(), nullable=True))

    op.execute(sa.text("UPDATE agent_turns SET finish_signal = termination"))

    with op.batch_alter_table("agent_turns") as batch_op:
        batch_op.drop_column("termination")
