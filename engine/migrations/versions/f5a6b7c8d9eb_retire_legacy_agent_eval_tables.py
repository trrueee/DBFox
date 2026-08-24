"""Retire historical Agent evaluation tables left behind by the Data cutover.

Revision ID: f5a6b7c8d9eb
Revises: f4a5b6c7d8ea

The evaluation subsystem moved to ``verification/`` and these tables have no
current runtime owner.  Some pre-DLC databases retained rows referencing the
Core ``data_sources`` table after that table was migrated into dbfox.data,
which makes the otherwise valid metadata database fail its startup FK check.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f5a6b7c8d9eb"
down_revision: str | None = "f4a5b6c7d8ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RETIRED_TABLES_CHILD_FIRST = (
    "agent_eval_case_results",
    "agent_eval_runs",
    "agent_golden_tasks",
)


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in _RETIRED_TABLES_CHILD_FIRST:
        if table_name in existing:
            op.drop_table(table_name)


def downgrade() -> None:
    # The retired evaluation rows were never a product fact source. Recreating
    # empty legacy tables would imply a supported runtime contract that no
    # longer exists, so this data-retirement migration is intentionally one-way.
    pass
