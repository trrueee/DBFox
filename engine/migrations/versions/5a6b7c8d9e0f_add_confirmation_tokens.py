"""make confirmation tokens part of the metadata schema contract

Revision ID: 5a6b7c8d9e0f
Revises: 4e7f9a1b2c3d
Create Date: 2026-07-11

The previous confirmation manager issued ad-hoc SQLite DDL at request time.
This revision adopts an already-created legacy table when it has the required
shape, and otherwise creates the canonical table through Alembic.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5a6b7c8d9e0f"
down_revision: Union[str, Sequence[str], None] = "4e7f9a1b2c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "confirmation_tokens"
_EXPIRY_INDEX = "ix_confirmation_tokens_expires_at"
_REQUIRED_COLUMNS = {
    "token",
    "expires_at",
    "datasource_id",
    "action",
    "details_json",
    "expected_confirm_text",
}


def _column_names(bind: sa.Connection) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(_TABLE_NAME)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE_NAME):
        op.create_table(
            _TABLE_NAME,
            sa.Column("token", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Float(), nullable=False),
            sa.Column("datasource_id", sa.Text(), nullable=False),
            sa.Column("action", sa.Text(), nullable=False),
            sa.Column("details_json", sa.Text(), nullable=False),
            sa.Column("expected_confirm_text", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("token"),
        )
    else:
        missing = _REQUIRED_COLUMNS - _column_names(bind)
        if missing:
            raise RuntimeError(
                "confirmation token table has an unsupported legacy shape; "
                f"missing columns: {sorted(missing)!r}"
            )

    index_names = {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE_NAME)}
    if _EXPIRY_INDEX not in index_names:
        op.create_index(_EXPIRY_INDEX, _TABLE_NAME, ["expires_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE_NAME):
        return
    index_names = {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE_NAME)}
    if _EXPIRY_INDEX in index_names:
        op.drop_index(_EXPIRY_INDEX, table_name=_TABLE_NAME)
    op.drop_table(_TABLE_NAME)
