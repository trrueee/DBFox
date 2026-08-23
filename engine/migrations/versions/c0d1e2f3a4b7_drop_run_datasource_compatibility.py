"""Drop retired datasource compatibility columns from Agent Run storage.

Revision ID: c0d1e2f3a4b7
Revises: c0d1e2f3a4b6

Run authority has one durable source: the admitted Input's frozen
``resource_refs_json``.  The nullable datasource columns were no longer
written by admission and keeping them offered a second, ambiguous authority
identity.  Session memory keeps its domain projection JSON; only the obsolete
Core foreign-key column is removed here.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c0d1e2f3a4b7"
down_revision: str | None = "c0d1e2f3a4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_index("ix_agent_runs_datasource")
        batch_op.drop_column("datasource_id")
        batch_op.drop_column("datasource_generation")

    with op.batch_alter_table("agent_session_memories") as batch_op:
        batch_op.drop_index("ix_agent_session_memories_datasource")
        batch_op.drop_column("datasource_id")


def downgrade() -> None:
    # These fields are compatibility projections in the preceding release, not
    # authority.  Restoring them as nullable/zero is lossless for the current
    # model and deliberately avoids inventing a database identity from generic
    # multi-resource refs.
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("datasource_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "datasource_generation",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_foreign_key(
            "fk_agent_runs_datasource_id_data_sources",
            "data_sources",
            ["datasource_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_agent_runs_datasource",
            ["datasource_id"],
            unique=False,
        )

    with op.batch_alter_table("agent_session_memories") as batch_op:
        batch_op.add_column(sa.Column("datasource_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_agent_session_memories_datasource_id_data_sources",
            "data_sources",
            ["datasource_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_agent_session_memories_datasource",
            ["datasource_id"],
            unique=False,
        )
