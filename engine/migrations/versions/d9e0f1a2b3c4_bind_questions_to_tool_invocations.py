"""bind clarification questions to their native tool calls

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
"""

from alembic import op
import sqlalchemy as sa


revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_question_requests") as batch:
        batch.add_column(
            sa.Column("tool_invocation_id", sa.String(), nullable=False)
        )
        batch.create_unique_constraint(
            "uq_agent_question_requests_tool_invocation",
            ["tool_invocation_id"],
        )
        batch.create_foreign_key(
            "fk_agent_question_requests_tool_invocation",
            "agent_tool_invocations",
            ["tool_invocation_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_question_requests") as batch:
        batch.drop_constraint(
            "fk_agent_question_requests_tool_invocation",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "uq_agent_question_requests_tool_invocation",
            type_="unique",
        )
        batch.drop_column("tool_invocation_id")
