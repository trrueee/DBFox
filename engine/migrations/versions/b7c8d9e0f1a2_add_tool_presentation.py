"""freeze tool presentation metadata on invocations

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_HISTORICAL_PRESENTATION = (
    '{"category":"manage","progress":"none","title":"工具操作",'
    '"visibility":"developer"}'
)


def upgrade() -> None:
    # SQLite batch mode derives one final table definition for every operation
    # in a block. Adding a non-null column and removing its default in that same
    # block therefore leaves historical rows with no value during the table copy.
    # Keep the backfill explicit so the migration is correct on every dialect.
    with op.batch_alter_table("agent_tool_invocations") as batch:
        batch.add_column(
            sa.Column(
                "presentation_json",
                sa.Text(),
                nullable=True,
            )
        )

    op.execute(
        sa.text(
            "UPDATE agent_tool_invocations "
            "SET presentation_json = :presentation "
            "WHERE presentation_json IS NULL"
        ).bindparams(presentation=_HISTORICAL_PRESENTATION)
    )

    with op.batch_alter_table("agent_tool_invocations") as batch:
        batch.alter_column(
            "presentation_json",
            existing_type=sa.Text(),
            existing_nullable=True,
            nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_tool_invocations") as batch:
        batch.drop_column("presentation_json")
