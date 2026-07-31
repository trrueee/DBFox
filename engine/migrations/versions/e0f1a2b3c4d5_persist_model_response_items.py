"""persist native model response items per agent turn

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
"""

from alembic import op
import sqlalchemy as sa


revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_turns") as batch:
        batch.add_column(sa.Column("message_phase", sa.String(), nullable=True))
        batch.add_column(
            sa.Column(
                "response_items_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_turns") as batch:
        batch.drop_column("response_items_json")
        batch.drop_column("message_phase")
