"""Drop retired datasource/table context columns from Conversations.

Revision ID: b9c0d1e2f3a5
Revises: a8b9c0d1e2f4
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b9c0d1e2f3a5"
down_revision: str | None = "a8b9c0d1e2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch_op:
        batch_op.drop_index("ix_agent_sessions_datasource")
        batch_op.drop_column("datasource_id")
        batch_op.drop_column("context_tables_json")


def downgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "context_tables_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )
        batch_op.add_column(
            sa.Column("datasource_id", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_agent_sessions_datasource_id_data_sources",
            "data_sources",
            ["datasource_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_agent_sessions_datasource",
            ["datasource_id"],
            unique=False,
        )

    # The preceding intent migration is the only remaining authority identity.
    # Restore a legacy datasource only when that identity still resolves to a
    # Core DataSource; later DLC-only identities deliberately remain NULL so the
    # older project-scope downgrade can reject an unrepresentable state.
    op.execute(sa.text("""
        UPDATE agent_sessions
           SET datasource_id = (
               SELECT intent.resource_id
                 FROM conversation_resource_intents AS intent
                 JOIN data_sources AS datasource
                   ON datasource.id = intent.resource_id
                WHERE intent.conversation_id = agent_sessions.id
                  AND intent.kind = 'database'
                ORDER BY intent.position
                LIMIT 1
           )
         WHERE datasource_id IS NULL
    """))
