"""Move the final Project workspace roots into dbfox.workspace and drop the column.

Revision ID: c0d1e2f3a4b6
Revises: b9c0d1e2f3a5
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from engine.migrations.workspace_dlc_state import migrate_legacy_workspace_data


revision: str = "c0d1e2f3a4b6"
down_revision: str | None = "b9c0d1e2f3a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # f7 imported roots that existed at its original cutover. Run the idempotent
    # importer once more so roots written by an older app between f7 and this
    # release cannot be lost before the Core column disappears.
    migrate_legacy_workspace_data(op.get_bind())
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("workspace_root")


def downgrade() -> None:
    # DLC state remains authoritative and recoverable. Reintroducing a nullable
    # legacy column is sufficient for the older schema; copying paths back would
    # create a second fact source and make subsequent upgrades ambiguous.
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("workspace_root", sa.String(), nullable=True))
