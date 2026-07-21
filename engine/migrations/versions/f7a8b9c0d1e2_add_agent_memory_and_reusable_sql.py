"""add agent memory and reusable sql

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-23
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sql_fingerprint(sql: str) -> str:
    normalized = " ".join(sql.strip().lower().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sql_{digest[:24]}"


def upgrade() -> None:
    op.create_table(
        "agent_session_memories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("datasource_id", sa.String(), nullable=False),
        sa.Column("conversation_summary", sa.Text(), nullable=True),
        sa.Column("summary_cursor_message_id", sa.String(), nullable=True),
        sa.Column("memory_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["datasource_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_agent_session_memories_session"),
    )
    op.create_index(
        "ix_agent_session_memories_datasource",
        "agent_session_memories",
        ["datasource_id"],
    )

    op.create_table(
        "reusable_sqls",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("safe_sql", sa.Text(), nullable=False),
        sa.Column("sql_fingerprint", sa.String(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("involved_tables_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("result_columns_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source_artifact_id", sa.String(), nullable=True),
        sa.Column("source_sql_artifact_id", sa.String(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_used_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "sql_fingerprint", name="uq_reusable_sqls_ds_fingerprint"),
    )
    op.create_index("ix_reusable_sqls_datasource", "reusable_sqls", ["data_source_id"])
    op.create_index("ix_reusable_sqls_fingerprint", "reusable_sqls", ["sql_fingerprint"])

    bind = op.get_bind()
    if not sa.inspect(bind).has_table("golden_sqls"):
        return

    now = datetime.now(UTC)
    rows = bind.execute(
        sa.text("SELECT data_source_id, question, golden_sql, created_at FROM golden_sqls")
    ).mappings()
    seen: set[tuple[str, str]] = set()
    for row in rows:
        safe_sql = str(row["golden_sql"] or "").strip()
        if not safe_sql:
            continue
        datasource_id = str(row["data_source_id"])
        fingerprint = _sql_fingerprint(safe_sql)
        key = (datasource_id, fingerprint)
        if key in seen:
            continue
        seen.add(key)
        created_at = row["created_at"] or now
        bind.execute(
            sa.text(
                """
                INSERT INTO reusable_sqls (
                    id, data_source_id, question, safe_sql, sql_fingerprint,
                    purpose, involved_tables_json, result_columns_json,
                    usage_count, verified, last_used_at, created_at, updated_at
                )
                VALUES (
                    :id, :data_source_id, :question, :safe_sql, :sql_fingerprint,
                    :purpose, :involved_tables_json, :result_columns_json,
                    :usage_count, :verified, :last_used_at, :created_at, :updated_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "data_source_id": datasource_id,
                "question": row["question"],
                "safe_sql": safe_sql,
                "sql_fingerprint": fingerprint,
                "purpose": "Migrated from legacy golden_sqls.",
                "involved_tables_json": "[]",
                "result_columns_json": "[]",
                "usage_count": 1,
                "verified": True,
                "last_used_at": created_at,
                "created_at": created_at,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_reusable_sqls_fingerprint", table_name="reusable_sqls")
    op.drop_index("ix_reusable_sqls_datasource", table_name="reusable_sqls")
    op.drop_table("reusable_sqls")
    op.drop_index("ix_agent_session_memories_datasource", table_name="agent_session_memories")
    op.drop_table("agent_session_memories")
