"""add_agent_persistence_tables

Revision ID: b1c2d3e4f5a6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_sessions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('datasource_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['datasource_id'], ['data_sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_sessions_datasource', 'agent_sessions', ['datasource_id'])
    op.create_index('ix_agent_sessions_created', 'agent_sessions', ['created_at'])

    op.create_table(
        'agent_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('parent_run_id', sa.String(), nullable=True),
        sa.Column('datasource_id', sa.String(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='running'),
        sa.Column('response_json', sa.Text(), nullable=True),
        sa.Column('context_summary', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['datasource_id'], ['data_sources.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_runs_session', 'agent_runs', ['session_id'])
    op.create_index('ix_agent_runs_datasource', 'agent_runs', ['datasource_id'])
    op.create_index('ix_agent_runs_created', 'agent_runs', ['created_at'])

    op.create_table(
        'agent_artifacts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('semantic_id', sa.String(), nullable=True),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('produced_by_step', sa.String(), nullable=True),
        sa.Column('depends_on_json', sa.Text(), nullable=True),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('presentation_json', sa.Text(), nullable=False),
        sa.Column('refs_json', sa.Text(), nullable=True),
        sa.Column('sequence', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_artifacts_run', 'agent_artifacts', ['run_id'])
    op.create_index('ix_agent_artifacts_session', 'agent_artifacts', ['session_id'])

    op.create_table(
        'agent_runtime_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('event_json', sa.Text(), nullable=False),
        sa.Column('created_at_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_runtime_events_run', 'agent_runtime_events', ['run_id'])
    op.create_index('ix_agent_runtime_events_session', 'agent_runtime_events', ['session_id'])

    op.create_table(
        'agent_trace_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('event_json', sa.Text(), nullable=False),
        sa.Column('created_at_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_trace_events_run', 'agent_trace_events', ['run_id'])
    op.create_index('ix_agent_trace_events_session', 'agent_trace_events', ['session_id'])


def downgrade() -> None:
    op.drop_table('agent_trace_events')
    op.drop_table('agent_runtime_events')
    op.drop_table('agent_artifacts')
    op.drop_table('agent_runs')
    op.drop_table('agent_sessions')
