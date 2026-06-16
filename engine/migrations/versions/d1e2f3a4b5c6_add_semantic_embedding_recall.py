"""add semantic embedding recall columns

Revision ID: d1e2f3a4b5c6
Revises: a6b7c8d9e0f1
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add enable_embedding_recall to data_sources, and embedding_blob & embedding_synced_at to semantic_aliases."""
    with op.batch_alter_table("data_sources", schema=None) as batch_op:
        batch_op.add_column(sa.Column("enable_embedding_recall", sa.Boolean(), server_default="0", nullable=False))
    with op.batch_alter_table("semantic_aliases", schema=None) as batch_op:
        batch_op.add_column(sa.Column("embedding_blob", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("embedding_synced_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove semantic embedding recall columns."""
    with op.batch_alter_table("semantic_aliases", schema=None) as batch_op:
        batch_op.drop_column("embedding_synced_at")
        batch_op.drop_column("embedding_blob")
    with op.batch_alter_table("data_sources", schema=None) as batch_op:
        batch_op.drop_column("enable_embedding_recall")
