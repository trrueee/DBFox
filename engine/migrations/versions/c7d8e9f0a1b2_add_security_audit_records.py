"""add security audit records

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-07-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "security_audit_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_audit_created", "security_audit_records", ["created_at"])
    op.create_index("ix_security_audit_action", "security_audit_records", ["action", "created_at"])
    op.create_index("ix_security_audit_session", "security_audit_records", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_security_audit_session", table_name="security_audit_records")
    op.drop_index("ix_security_audit_action", table_name="security_audit_records")
    op.drop_index("ix_security_audit_created", table_name="security_audit_records")
    op.drop_table("security_audit_records")
