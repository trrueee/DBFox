"""Migrate Project workspace roots into DLC-owned state.

Revision ID: f7a8b9c0d1e3
Revises: e6f7a8b9c0d2
"""

from collections.abc import Sequence

from alembic import op

from engine.migrations.workspace_dlc_state import migrate_legacy_workspace_data

revision: str = "f7a8b9c0d1e3"
down_revision: str | None = "e6f7a8b9c0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    migrate_legacy_workspace_data(op.get_bind())


def downgrade() -> None:
    # The target store remains authoritative and recoverable. A metadata
    # downgrade must not delete or silently copy external user paths.
    pass
