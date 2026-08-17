"""Split ToolInvocation identity into declared_version and contract_hash.

Revision ID: a2b3c4d5e6f7
Revises: d7e8f9a0b1c2
Create Date: 2026-08-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_tool_invocations",
        sa.Column("declared_version", sa.String(), nullable=True),
    )
    op.add_column(
        "agent_tool_invocations",
        sa.Column("contract_hash", sa.String(), nullable=True),
    )
    op.execute(
        """
        UPDATE agent_tool_invocations
        SET contract_hash = tool_version
        WHERE contract_hash IS NULL
        """
    )
    op.execute(
        """
        UPDATE agent_tool_invocations
        SET declared_version = CASE
            WHEN tool_version LIKE 'sha256:%' THEN '1'
            ELSE tool_version
        END
        WHERE declared_version IS NULL
        """
    )
    with op.batch_alter_table("agent_tool_invocations") as batch_op:
        batch_op.alter_column("declared_version", nullable=False)
        batch_op.alter_column("contract_hash", nullable=False)
        batch_op.drop_column("tool_version")


def downgrade() -> None:
    with op.batch_alter_table("agent_tool_invocations") as batch_op:
        batch_op.add_column(sa.Column("tool_version", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE agent_tool_invocations
        SET tool_version = contract_hash
        WHERE tool_version IS NULL
        """
    )
    with op.batch_alter_table("agent_tool_invocations") as batch_op:
        batch_op.alter_column("tool_version", nullable=False)
        batch_op.drop_column("declared_version")
        batch_op.drop_column("contract_hash")
