"""Persist Sidecar-owned local execution jobs and retained output."""

import sqlalchemy as sa
from alembic import op

revision = "0f6ae97c42b1"
down_revision = "f8a9b0c1d2ee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_execution_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("invocation_id", sa.String(), nullable=False, unique=True),
        sa.Column("approval_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("workspace_generation", sa.String(), nullable=False),
        sa.Column("engine_generation", sa.String(), nullable=False),
        sa.Column("command_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("reason", sa.String()),
        sa.Column("root_exit_code", sa.BigInteger()),
        sa.Column("active_processes", sa.Integer()),
        sa.Column("stdin_open", sa.Boolean(), nullable=False),
        sa.Column("output_finalized", sa.Boolean(), nullable=False),
        sa.Column("first_cursor", sa.BigInteger(), nullable=False),
        sa.Column("last_cursor", sa.BigInteger(), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("retained_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("finished_at", sa.BigInteger()),
    )
    op.create_index("ix_local_execution_jobs_session_created", "local_execution_jobs", ["session_id", "created_at"])
    op.create_index("ix_local_execution_jobs_finished", "local_execution_jobs", ["finished_at"])
    op.create_table(
        "local_execution_logs",
        sa.Column("job_id", sa.String(), sa.ForeignKey("local_execution_jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("cursor", sa.BigInteger(), primary_key=True),
        sa.Column("stream", sa.String(), nullable=False),
        sa.Column("byte_end", sa.BigInteger(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("local_execution_logs")
    op.drop_table("local_execution_jobs")
