"""Make every admitted Input carry one canonical frozen resource-ref set.

Revision ID: c0d1e2f3a4b8
Revises: c0d1e2f3a4b7

The empty JSON list is the sole durable representation of zero authority.
Older NULL rows are intentionally backfilled to that fail-closed value before
the column becomes required.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c0d1e2f3a4b8"
down_revision: str | None = "c0d1e2f3a4b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE agent_session_inputs "
            "SET resource_refs_json = '[]' "
            "WHERE resource_refs_json IS NULL"
        )
    )
    with op.batch_alter_table("agent_session_inputs") as batch_op:
        batch_op.alter_column(
            "resource_refs_json",
            existing_type=sa.Text(),
            nullable=False,
            server_default="[]",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_session_inputs") as batch_op:
        batch_op.alter_column(
            "resource_refs_json",
            existing_type=sa.Text(),
            nullable=True,
            server_default=None,
        )
