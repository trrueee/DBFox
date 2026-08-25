"""Add typed Input references and exact ToolInvocation resources.

Revision ID: f6a7b8c9d0ec
Revises: f5a6b7c8d9eb
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0ec"
down_revision = "f5a6b7c8d9eb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_session_inputs") as batch:
        batch.add_column(
            sa.Column(
                "references_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )
    with op.batch_alter_table("agent_tool_invocations") as batch:
        batch.add_column(
            sa.Column(
                "resource_refs_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )
    # Existing invocations were admitted under whole-Input frozen authority.
    # Preserve that exact historical authority once at the migration boundary;
    # new invocations persist their own minimal resource set directly.
    op.execute(
        """
        UPDATE agent_tool_invocations
        SET resource_refs_json = COALESCE(
            (
                SELECT inputs.resource_refs_json
                FROM agent_runs AS runs
                JOIN agent_session_inputs AS inputs ON inputs.id = runs.input_id
                WHERE runs.id = agent_tool_invocations.run_id
            ),
            '[]'
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("agent_tool_invocations") as batch:
        batch.drop_column("resource_refs_json")
    with op.batch_alter_table("agent_session_inputs") as batch:
        batch.drop_column("references_json")
