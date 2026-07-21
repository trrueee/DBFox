"""create the independent durable Agent runtime v2 tables

Revision ID: 8d9e0f1a2b3c
Revises: 7c8d9e0f1a2b
Create Date: 2026-07-11

The legacy ``agent_runs``/``agent_approvals`` tables remain available only
until first-party callers are moved.  This migration creates a separate,
run-scoped lifecycle with immutable connection identity, optimistic versions,
checkpoint-bound approval consumption, and an ordered transactional outbox.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8d9e0f1a2b3c"
down_revision: Union[str, Sequence[str], None] = "7c8d9e0f1a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runtime_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("datasource_id", sa.String(), nullable=False),
        sa.Column("datasource_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_credential_id", sa.String(), nullable=False),
        sa.Column("checkpoint_namespace", sa.String(), nullable=False),
        sa.Column("checkpoint_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_id", sa.String(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(), nullable=False, server_default="created"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outbox_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("version >= 0", name="ck_agent_runtime_runs_version_nonnegative"),
        sa.CheckConstraint(
            "checkpoint_version >= 0",
            name="ck_agent_runtime_runs_checkpoint_version_nonnegative",
        ),
        sa.CheckConstraint(
            "outbox_sequence >= 0",
            name="ck_agent_runtime_runs_outbox_sequence_nonnegative",
        ),
        sa.CheckConstraint(
            "status IN ('created', 'running', 'waiting_approval', 'cancelling', "
            "'cancelled', 'completed', 'failed')",
            name="ck_agent_runtime_runs_status",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["datasource_id"], ["data_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_namespace", name="uq_agent_runtime_runs_checkpoint_namespace"),
        sa.UniqueConstraint("execution_id", name="uq_agent_runtime_runs_execution_id"),
    )
    op.create_index("ix_agent_runtime_runs_conversation", "agent_runtime_runs", ["conversation_id"])
    op.create_index("ix_agent_runtime_runs_datasource", "agent_runtime_runs", ["datasource_id"])
    op.create_index("ix_agent_runtime_runs_status", "agent_runtime_runs", ["status"])

    op.create_table(
        "agent_runtime_checkpoints",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checkpoint_namespace", sa.String(), nullable=False),
        sa.Column("checkpoint_ref", sa.Text(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_agent_runtime_checkpoints_version_positive"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runtime_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "version", name="uq_agent_runtime_checkpoints_run_version"),
    )
    op.create_index("ix_agent_runtime_checkpoints_run", "agent_runtime_checkpoints", ["run_id"])

    op.create_table(
        "agent_runtime_approvals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("checkpoint_id", sa.String(), nullable=False),
        sa.Column("checkpoint_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_action_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version >= 0", name="ck_agent_runtime_approvals_version_nonnegative"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired')",
            name="ck_agent_runtime_approvals_status",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runtime_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["agent_runtime_checkpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runtime_approvals_run", "agent_runtime_approvals", ["run_id"])
    op.create_index("ix_agent_runtime_approvals_status", "agent_runtime_approvals", ["status"])

    op.create_table(
        "agent_runtime_outbox_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "sequence > 0",
            name="ck_agent_runtime_outbox_events_sequence_positive",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runtime_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_agent_runtime_outbox_events_run_sequence"),
    )
    op.create_index(
        "ix_agent_runtime_outbox_events_run_sequence",
        "agent_runtime_outbox_events",
        ["run_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runtime_outbox_events_run_sequence", table_name="agent_runtime_outbox_events")
    op.drop_table("agent_runtime_outbox_events")
    op.drop_index("ix_agent_runtime_approvals_status", table_name="agent_runtime_approvals")
    op.drop_index("ix_agent_runtime_approvals_run", table_name="agent_runtime_approvals")
    op.drop_table("agent_runtime_approvals")
    op.drop_index("ix_agent_runtime_checkpoints_run", table_name="agent_runtime_checkpoints")
    op.drop_table("agent_runtime_checkpoints")
    op.drop_index("ix_agent_runtime_runs_status", table_name="agent_runtime_runs")
    op.drop_index("ix_agent_runtime_runs_datasource", table_name="agent_runtime_runs")
    op.drop_index("ix_agent_runtime_runs_conversation", table_name="agent_runtime_runs")
    op.drop_table("agent_runtime_runs")
