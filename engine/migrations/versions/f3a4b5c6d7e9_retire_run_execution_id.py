"""Retire legacy Core fields owned by the former Data runtime.

Revision ID: f3a4b5c6d7e9
Revises: e2f3a4b5c6d8

ToolInvocation IDs are the stable execution identities. Cancellation is
dispatched through the owning Tool implementation, so AgentRun no longer
carries a parallel query execution identifier. DLC context contributors own
domain memory, so Core also drops the retired Catalog projection shadow.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f3a4b5c6d7e9"
down_revision: str | None = "e2f3a4b5c6d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_column("execution_id")
    with op.batch_alter_table("agent_session_memories") as batch_op:
        batch_op.drop_column("memory_v4_json")
    with op.batch_alter_table("agent_evidence") as batch_op:
        batch_op.drop_column("query_fingerprint")


def downgrade() -> None:
    with op.batch_alter_table("agent_evidence") as batch_op:
        batch_op.add_column(
            sa.Column(
                "query_fingerprint",
                sa.String(),
                nullable=False,
                server_default="",
            )
        )
    with op.batch_alter_table("agent_session_memories") as batch_op:
        batch_op.add_column(sa.Column("memory_v4_json", sa.Text(), nullable=True))
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("execution_id", sa.String(), nullable=True))
