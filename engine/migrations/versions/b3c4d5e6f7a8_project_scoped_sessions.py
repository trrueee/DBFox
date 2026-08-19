"""Make Agent sessions project-scoped with frozen input resource refs.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# FK naming convention for batch mode
_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade() -> None:
    # 1. Add project_id to agent_sessions
    op.add_column(
        "agent_sessions",
        sa.Column("project_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_agent_sessions_project",
        "agent_sessions",
        ["project_id"],
    )

    # Backfill project_id from datasource → project relationship
    op.execute("""
        UPDATE agent_sessions
        SET project_id = (
            SELECT data_sources.project_id
            FROM data_sources
            WHERE data_sources.id = agent_sessions.datasource_id
        )
        WHERE project_id IS NULL
    """)

    # 2. Make datasource_id nullable and update FK for agent_sessions
    with op.batch_alter_table(
        "agent_sessions",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.alter_column(
            "datasource_id",
            existing_type=sa.String(),
            nullable=True,
        )
        batch.drop_constraint(
            "fk_agent_sessions_datasource_id_data_sources",
            type_="foreignkey",
        )
        batch.create_foreign_key(
            "fk_agent_sessions_datasource_id_data_sources",
            "data_sources",
            ["datasource_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_agent_sessions_project_id_projects",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # 3. Make datasource_id nullable and update FK for agent_runs
    with op.batch_alter_table(
        "agent_runs",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.alter_column(
            "datasource_id",
            existing_type=sa.String(),
            nullable=True,
        )
        batch.drop_constraint(
            "fk_agent_runs_datasource_id_data_sources",
            type_="foreignkey",
        )
        batch.create_foreign_key(
            "fk_agent_runs_datasource_id_data_sources",
            "data_sources",
            ["datasource_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 3.5. Make datasource_id nullable and update FK for agent_session_memories
    with op.batch_alter_table(
        "agent_session_memories",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.alter_column(
            "datasource_id",
            existing_type=sa.String(),
            nullable=True,
        )
        batch.drop_constraint(
            "fk_agent_session_memories_datasource_id_data_sources",
            type_="foreignkey",
        )
        batch.create_foreign_key(
            "fk_agent_session_memories_datasource_id_data_sources",
            "data_sources",
            ["datasource_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 4. Add resource_refs_json to agent_session_inputs
    op.add_column(
        "agent_session_inputs",
        sa.Column("resource_refs_json", sa.Text(), nullable=True),
    )

    # 5. Index for efficient input resource lookup
    op.create_index(
        "ix_agent_session_inputs_run",
        "agent_session_inputs",
        ["run_id"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    null_sessions = (
        conn.execute(
            sa.text("SELECT count(*) FROM agent_sessions WHERE datasource_id IS NULL")
        ).scalar()
        or 0
    )
    null_runs = (
        conn.execute(
            sa.text("SELECT count(*) FROM agent_runs WHERE datasource_id IS NULL")
        ).scalar()
        or 0
    )
    null_memories = (
        conn.execute(
            sa.text(
                "SELECT count(*) FROM agent_session_memories WHERE datasource_id IS NULL"
            )
        ).scalar()
        or 0
    )

    if null_sessions > 0 or null_runs > 0 or null_memories > 0:
        raise RuntimeError(
            "Cannot downgrade project-scoped sessions while datasource-less Agent "
            f"sessions/runs/memory rows exist (null sessions: {null_sessions}, "
            f"runs: {null_runs}, memories: {null_memories})."
        )

    op.drop_index("ix_agent_session_inputs_run", table_name="agent_session_inputs")
    op.drop_column("agent_session_inputs", "resource_refs_json")

    with op.batch_alter_table(
        "agent_runs",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.drop_constraint(
            "fk_agent_runs_datasource_id_data_sources",
            type_="foreignkey",
        )
        batch.create_foreign_key(
            "fk_agent_runs_datasource_id_data_sources",
            "data_sources",
            ["datasource_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.alter_column(
            "datasource_id",
            existing_type=sa.String(),
            nullable=False,
        )

    with op.batch_alter_table(
        "agent_session_memories",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.drop_constraint(
            "fk_agent_session_memories_datasource_id_data_sources",
            type_="foreignkey",
        )
        batch.create_foreign_key(
            "fk_agent_session_memories_datasource_id_data_sources",
            "data_sources",
            ["datasource_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.alter_column(
            "datasource_id",
            existing_type=sa.String(),
            nullable=False,
        )

    with op.batch_alter_table(
        "agent_sessions",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.drop_constraint(
            "fk_agent_sessions_project_id_projects",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_agent_sessions_datasource_id_data_sources",
            type_="foreignkey",
        )
        batch.create_foreign_key(
            "fk_agent_sessions_datasource_id_data_sources",
            "data_sources",
            ["datasource_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.alter_column(
            "datasource_id",
            existing_type=sa.String(),
            nullable=False,
        )

    op.drop_index("ix_agent_sessions_project", table_name="agent_sessions")
    op.drop_column("agent_sessions", "project_id")
