"""Add durable generic Conversation resource intent.

Revision ID: e6f7a8b9c0d2
Revises: d5e6f7a8b9c1
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e6f7a8b9c0d2"
down_revision: str | None = "d5e6f7a8b9c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_resource_intents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=256), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "kind",
            "resource_id",
            name="uq_conversation_resource_intent_identity",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "position",
            name="uq_conversation_resource_intent_position",
        ),
    )
    op.create_index(
        "ix_conversation_resource_intents_conversation",
        "conversation_resource_intents",
        ["conversation_id"],
        unique=False,
    )

    # Preserve existing explicit Conversation→Datasource behavior as visible,
    # removable intent. Workspace membership is intentionally not auto-seeded.
    op.execute(sa.text("""
        INSERT INTO conversation_resource_intents
            (id, conversation_id, kind, resource_id, position, created_at)
        SELECT
            lower(hex(randomblob(16))),
            id,
            'database',
            datasource_id,
            0,
            COALESCE(created_at, CURRENT_TIMESTAMP)
        FROM agent_sessions
        WHERE datasource_id IS NOT NULL
    """))


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_resource_intents_conversation",
        table_name="conversation_resource_intents",
    )
    op.drop_table("conversation_resource_intents")
