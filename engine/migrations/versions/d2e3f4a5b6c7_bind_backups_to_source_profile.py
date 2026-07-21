"""bind backups to their source connection profile

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-13
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing backups intentionally remain unbound and therefore unrestorable.
    # There is no trustworthy way to reconstruct their original connection profile.
    with op.batch_alter_table("backup_records") as batch_op:
        batch_op.add_column(sa.Column("source_connection_generation", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("source_profile_fingerprint", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source_database_name", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("backup_records") as batch_op:
        batch_op.drop_column("source_database_name")
        batch_op.drop_column("source_profile_fingerprint")
        batch_op.drop_column("source_connection_generation")
