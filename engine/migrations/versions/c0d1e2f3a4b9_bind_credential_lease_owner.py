"""Bind claimed credential leases to their durable capability owner.

Revision ID: c0d1e2f3a4b9
Revises: c0d1e2f3a4b8

Before the generic DLC operation host existed, every claimed lease belonged to
the built-in Data capability.  Recording that fact during migration lets
recovery use one exact owner probe instead of asking every active capability.
Pending leases intentionally remain unbound until an operation claims them.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c0d1e2f3a4b9"
down_revision: str | None = "c0d1e2f3a4b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("credential_leases") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("owner_operation", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("owner_project_id", sa.String(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE credential_leases
               SET owner_id = 'dbfox.data',
                   owner_operation = 'legacy.datasource'
             WHERE status IN ('claimed', 'committed')
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("credential_leases") as batch_op:
        batch_op.drop_column("owner_project_id")
        batch_op.drop_column("owner_operation")
        batch_op.drop_column("owner_id")
