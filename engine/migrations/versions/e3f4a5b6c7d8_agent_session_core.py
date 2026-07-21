"""establish the Agent session core

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch_op:
        batch_op.alter_column(
            "runtime_message_sequence",
            new_column_name="message_sequence",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("input_sequence", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("event_sequence", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("lease_owner", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("lease_token", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("selected_artifact_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("context_epoch", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "agent_session_inputs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("delivery_mode", sa.String(), nullable=False, server_default="queue"),
        sa.Column("selected_artifact_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("workspace_context_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("reply_to_request_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="admitted"),
        sa.Column("admitted_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["agent_messages.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_agent_session_inputs_sequence"),
        sa.UniqueConstraint("session_id", "idempotency_key", name="uq_agent_session_inputs_idempotency"),
    )
    op.create_index("ix_agent_session_inputs_status", "agent_session_inputs", ["session_id", "status", "sequence"])

    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("input_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("session_sequence", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("datasource_generation", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("lease_token", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("execution_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("current_turn_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("result_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_foreign_key("fk_agent_runs_input_id", "agent_session_inputs", ["input_id"], ["id"], ondelete="RESTRICT")

    op.create_table(
        "agent_turns",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("agent_definition_version", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("prompt_hash", sa.String(), nullable=False),
        sa.Column("context_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("context_hash", sa.String(), nullable=False),
        sa.Column("tool_materialization_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("tool_materialization_hash", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("reasoning_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("tool_calls_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("usage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("finish_signal", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_agent_turns_run_sequence"),
    )
    op.create_index("ix_agent_turns_session", "agent_turns", ["session_id", "created_at"])
    op.create_index("ix_agent_turns_status", "agent_turns", ["status"])

    with op.batch_alter_table("agent_approvals") as batch_op:
        batch_op.add_column(sa.Column("turn_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("tool_invocation_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("consumed_at", sa.DateTime(), nullable=True))

    op.create_table(
        "agent_tool_invocations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("provider_call_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("tool_version", sa.String(), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="requested"),
        sa.Column("policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("approval_id", sa.String(), nullable=True),
        sa.Column("recovery_policy", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_ref", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["agent_turns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["agent_approvals.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("turn_id", "provider_call_id", name="uq_agent_tool_invocations_provider_call"),
        sa.UniqueConstraint("idempotency_key", name="uq_agent_tool_invocations_idempotency"),
    )
    op.create_index("ix_agent_tool_invocations_run", "agent_tool_invocations", ["run_id", "created_at"])
    op.create_index("ix_agent_tool_invocations_status", "agent_tool_invocations", ["status"])

    op.create_table(
        "agent_observations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("tool_invocation_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("model_visible_summary", sa.Text(), nullable=False),
        sa.Column("structured_result_ref", sa.String(), nullable=True),
        sa.Column("artifact_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("facts_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["agent_turns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_invocation_id"], ["agent_tool_invocations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_agent_observations_run_sequence"),
        sa.UniqueConstraint("tool_invocation_id", name="uq_agent_observations_invocation"),
    )
    op.create_index("ix_agent_observations_session", "agent_observations", ["session_id", "created_at"])

    with op.batch_alter_table("agent_artifacts") as batch_op:
        batch_op.add_column(sa.Column("turn_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("payload_ref", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("relations_json", sa.Text(), nullable=False, server_default="[]"))

    op.create_table(
        "agent_evidence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("claim_id", sa.String(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("locator_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["agent_artifacts.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_agent_evidence_run", "agent_evidence", ["run_id"])
    op.create_index("ix_agent_evidence_artifact", "agent_evidence", ["artifact_id"])

    op.create_table(
        "agent_question_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("allow_free_text", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("response_message_id", sa.String(), nullable=True),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["agent_turns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["response_message_id"], ["agent_messages.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_agent_question_requests_run", "agent_question_requests", ["run_id"])
    op.create_index("ix_agent_question_requests_status", "agent_question_requests", ["status"])

    op.create_table(
        "agent_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("turn_id", sa.String(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["agent_turns.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_agent_events_session_sequence"),
    )
    op.create_index("ix_agent_events_run", "agent_events", ["run_id", "sequence"])
    op.create_index("ix_agent_events_session", "agent_events", ["session_id", "sequence"])

    # The Session Core is the sole durable Agent model. Remove the abandoned
    # graph-runtime projections so installed databases cannot expose two
    # competing sources of truth.
    for table_name in (
        "agent_runtime_artifacts",
        "agent_runtime_messages",
        "agent_runtime_outbox_events",
        "agent_runtime_approvals",
        "agent_runtime_checkpoints",
        "agent_runtime_runs",
        "agent_trace_events",
        "agent_runtime_events",
        "agent_checkpoints",
    ):
        op.drop_table(table_name)


def downgrade() -> None:
    op.drop_index("ix_agent_events_session", table_name="agent_events")
    op.drop_index("ix_agent_events_run", table_name="agent_events")
    op.drop_table("agent_events")
    op.drop_index("ix_agent_question_requests_status", table_name="agent_question_requests")
    op.drop_index("ix_agent_question_requests_run", table_name="agent_question_requests")
    op.drop_table("agent_question_requests")
    op.drop_index("ix_agent_evidence_artifact", table_name="agent_evidence")
    op.drop_index("ix_agent_evidence_run", table_name="agent_evidence")
    op.drop_table("agent_evidence")
    with op.batch_alter_table("agent_artifacts") as batch_op:
        for column in ("relations_json", "provenance_json", "payload_ref", "summary", "version", "turn_id"):
            batch_op.drop_column(column)
    op.drop_index("ix_agent_observations_session", table_name="agent_observations")
    op.drop_table("agent_observations")
    op.drop_index("ix_agent_tool_invocations_status", table_name="agent_tool_invocations")
    op.drop_index("ix_agent_tool_invocations_run", table_name="agent_tool_invocations")
    op.drop_table("agent_tool_invocations")
    with op.batch_alter_table("agent_approvals") as batch_op:
        for column in ("consumed_at", "version", "tool_invocation_id", "turn_id"):
            batch_op.drop_column(column)
    op.drop_index("ix_agent_turns_status", table_name="agent_turns")
    op.drop_index("ix_agent_turns_session", table_name="agent_turns")
    op.drop_table("agent_turns")
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_constraint("fk_agent_runs_input_id", type_="foreignkey")
        for column in (
            "cancel_requested", "result_json", "request_json", "current_turn_id", "execution_id",
            "lease_token", "version", "datasource_generation", "session_sequence", "input_id",
        ):
            batch_op.drop_column(column)
    op.drop_index("ix_agent_session_inputs_status", table_name="agent_session_inputs")
    op.drop_table("agent_session_inputs")
    with op.batch_alter_table("agent_sessions") as batch_op:
        for column in (
            "context_epoch", "selected_artifact_id", "lease_expires_at", "lease_token",
            "lease_owner", "event_sequence", "input_sequence",
        ):
            batch_op.drop_column(column)
        batch_op.alter_column(
            "message_sequence",
            new_column_name="runtime_message_sequence",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
