"""remove plaintext LLM invocation logs

Revision ID: 4e7f9a1b2c3d
Revises: 3c5d7e9f1a2b
Create Date: 2026-07-11

LLM prompts, model responses, provider error bodies, and free-form model
validation warnings are data-bearing values.  They are not safe diagnostic
telemetry and are removed without a compatibility reader or a debug opt-in.
Only non-sensitive operational metadata remains in ``llm_logs``.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4e7f9a1b2c3d"
down_revision: Union[str, Sequence[str], None] = "3c5d7e9f1a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PLAINTEXT_COLUMNS = (
    "prompt_text",
    "response_text",
    "error_message",
    "schema_validation_warnings",
)
_LEGACY_FAILURE_CODE = "LLM_INVOCATION_FAILED"


def _column_names(bind: sa.Connection, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("llm_logs"):
        return

    columns = _column_names(bind, "llm_logs")
    plaintext_columns = [column for column in _PLAINTEXT_COLUMNS if column in columns]
    has_error_code = "error_code" in columns
    if not plaintext_columns and has_error_code:
        # A previous model revision allowed arbitrary data in this field.  Do
        # not trust it merely because the obvious transcript columns are gone.
        if "prompt_hash" in columns:
            bind.execute(sa.text("UPDATE llm_logs SET prompt_hash = NULL"))
        return

    # Fresh installs after the baseline change have no plaintext columns.  The
    # same batch path also handles divergent pre-v2 databases safely on SQLite.
    with op.batch_alter_table("llm_logs", recreate="always") as batch_op:
        if not has_error_code:
            batch_op.add_column(sa.Column("error_code", sa.String(), nullable=True))
        for column in plaintext_columns:
            batch_op.drop_column(column)

    # Retain an intentionally generic code for legacy failures before their
    # provider error bodies are destroyed.  Never derive it from the text.
    if "error_message" in columns:
        bind.execute(
            sa.text(
                """
                UPDATE llm_logs
                SET error_code = :error_code
                WHERE status IS NOT NULL AND lower(status) NOT IN ('success', 'completed')
                """
            ),
            {"error_code": _LEGACY_FAILURE_CODE},
        )

    # The historic column accepted arbitrary strings, so it cannot prove that
    # its values are keyed, non-reversible fingerprints.  Clear it rather than
    # risk retaining a prompt under a misleading name; new ORM writes enforce
    # the hmac-sha256 fingerprint contract.
    if "prompt_hash" in columns:
        bind.execute(sa.text("UPDATE llm_logs SET prompt_hash = NULL"))


def downgrade() -> None:
    raise NotImplementedError(
        "plaintext LLM transcripts are intentionally destroyed and cannot be restored"
    )
