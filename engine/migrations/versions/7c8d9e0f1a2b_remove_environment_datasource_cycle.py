"""remove the redundant environment-to-datasource foreign-key cycle

Revision ID: 7c8d9e0f1a2b
Revises: 6b7c8d9e0f1a
Create Date: 2026-07-11

``data_sources.environment_id`` is the single authoritative association
between an endpoint and its managed environment.  The historical reverse
``database_environments.datasource_id`` duplicated that relationship and
created an unresolvable foreign-key cycle for metadata ordering and Alembic
autogeneration.  No production path reads the reverse value, so it is
intentionally destroyed rather than retained as a compatibility projection.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c8d9e0f1a2b"
down_revision: Union[str, Sequence[str], None] = "6b7c8d9e0f1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "database_environments"
_COLUMN_NAME = "datasource_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE_NAME):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE_NAME)}
    if _COLUMN_NAME not in columns:
        return

    with op.batch_alter_table(_TABLE_NAME, recreate="always") as batch_op:
        batch_op.drop_column(_COLUMN_NAME)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE_NAME):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE_NAME)}
    if _COLUMN_NAME in columns:
        return

    with op.batch_alter_table(_TABLE_NAME, recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                _COLUMN_NAME,
                sa.String(),
                sa.ForeignKey("data_sources.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
