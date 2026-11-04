"""Persist immutable conversation attachment identity and admission linkage."""
from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d0ed"
down_revision = "f6a7b8c9d0ec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("session_resource_retirements",
                    sa.Column("session_id", sa.String(), primary_key=True),
                    sa.Column("attachment_ids_json", sa.Text(), nullable=False, server_default="[]"),
                    sa.Column("delivered_owners_json", sa.Text(), nullable=False, server_default="[]"),
                    sa.Column("created_at", sa.DateTime(), nullable=False))
    with op.batch_alter_table("agent_session_inputs") as batch:
        batch.add_column(sa.Column("request_fingerprint", sa.String(64), nullable=True))
    op.create_table(
        "conversation_attachments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("upload_key", sa.String(128), nullable=False),
        sa.Column("first_input_id", sa.String(), nullable=True),
        sa.Column("first_input_sequence", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("session_id", "upload_key", name="uq_attachment_upload"),
        sa.CheckConstraint("byte_count > 0", name="ck_attachment_nonempty"),
    )
    op.create_index("ix_attachment_session_input", "conversation_attachments", ["session_id", "first_input_id"])


def downgrade() -> None:
    op.drop_table("session_resource_retirements")
    op.drop_table("conversation_attachments")
    with op.batch_alter_table("agent_session_inputs") as batch:
        batch.drop_column("request_fingerprint")
