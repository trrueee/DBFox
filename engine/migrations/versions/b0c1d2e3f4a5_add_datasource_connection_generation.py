"""fence managed datasource connection resources by generation

Revision ID: b0c1d2e3f4a5
Revises: a0b1c2d3e4f5
Create Date: 2026-07-12

Each committed connection configuration gets a monotonic generation.  It is
part of the in-memory pool/tunnel key and prevents an old profile from being
reused after host, SSH, TLS, or credential-reference rotation.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("data_sources", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "connection_generation",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("data_sources", schema=None) as batch_op:
        batch_op.drop_column("connection_generation")
