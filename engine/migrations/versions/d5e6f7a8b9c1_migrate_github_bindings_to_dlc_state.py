"""Migrate GitHub bindings into DLC-owned state.

Revision ID: d5e6f7a8b9c1
Revises: c5d6e7f8a9b0
"""

from collections.abc import Sequence

from alembic import op

from engine.migrations.github_dlc_state import migrate_legacy_github_data


revision: str = "d5e6f7a8b9c1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Target data is committed before its completion marker.  Historical Core
    # rows remain untouched so a failed upgrade is fully recoverable.
    migrate_legacy_github_data(op.get_bind())


def downgrade() -> None:
    # Cutover is intentionally one-way.  Never delete DLC-owned user data from
    # a metadata downgrade; the untouched historical rows remain available.
    pass
