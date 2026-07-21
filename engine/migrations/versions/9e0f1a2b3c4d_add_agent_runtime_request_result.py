"""persist v2 Agent request and terminal result payloads

Revision ID: 9e0f1a2b3c4d
Revises: 8d9e0f1a2b3c
Create Date: 2026-07-12

The v2 runner is detached from the HTTP/SSE request that starts it.  A
validated, secret-free request is therefore durable input to a resumed graph;
the terminal result is kept separately from the replayable outbox.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9e0f1a2b3c4d"
down_revision: Union[str, Sequence[str], None] = "8d9e0f1a2b3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runtime_runs",
        sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column("agent_runtime_runs", sa.Column("result_json", sa.Text(), nullable=True))
    # Keep the explicit default for SQLite/MySQL compatibility: every write
    # path supplies a validated payload, and the default protects historic rows
    # during rolling upgrades without inventing request content.


def downgrade() -> None:
    op.drop_column("agent_runtime_runs", "result_json")
    op.drop_column("agent_runtime_runs", "request_json")
