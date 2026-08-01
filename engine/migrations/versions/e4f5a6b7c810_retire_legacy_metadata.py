"""Retire metadata left behind by removed product architectures.

The retired product rows are intentionally not recoverable through downgrade.
Alembic's SQLite snapshot remains the recovery boundary for the removed data.
Opaque environment credential references are preserved as durable cleanup work
before their owning table is dropped; the application reconciles that work
against the external credential vault after the database transaction commits.

Revision ID: e4f5a6b7c810
Revises: d3e4f5a6b709
"""

from collections.abc import Sequence
from datetime import UTC, datetime
import json
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "e4f5a6b7c810"
down_revision: str | None = "d3e4f5a6b709"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enqueue_retired_environment_credentials() -> None:
    connection = op.get_bind()
    environment_ids = {
        str(value)
        for value in connection.execute(
            sa.text(
                """
                SELECT DISTINCT password_credential_id
                FROM database_environments
                WHERE password_credential_id IS NOT NULL
                  AND TRIM(password_credential_id) <> ''
                """
            )
        ).scalars()
    }
    if not environment_ids:
        return

    referenced_ids: set[str] = set()
    rows = connection.execute(
        sa.text(
            """
            SELECT password_credential_id,
                   ssh_password_credential_id,
                   ssh_key_passphrase_credential_id
            FROM data_sources
            """
        )
    )
    for row in rows:
        referenced_ids.update(str(value) for value in row if value)

    retired_ids = sorted(environment_ids - referenced_ids)
    if not retired_ids:
        return

    now = datetime.now(UTC)
    connection.execute(
        sa.text(
            """
            INSERT INTO credential_leases (
                id, credential_ids_json, status, version, created_at,
                expires_at, cleanup_started_at
            ) VALUES (
                :id, :credential_ids_json, 'cleanup_pending', 0, :created_at,
                :expires_at, :cleanup_started_at
            )
            """
        ),
        {
            "id": f"lease_retired_environment_{uuid4().hex}",
            "credential_ids_json": json.dumps(retired_ids, separators=(",", ":")),
            "created_at": now,
            "expires_at": now,
            "cleanup_started_at": now,
        },
    )


def upgrade() -> None:
    _enqueue_retired_environment_credentials()

    op.drop_index("ix_workspace_table_scopes_project_ds", table_name="workspace_table_scopes")
    op.drop_table("workspace_table_scopes")

    op.drop_index("ix_reusable_sqls_fingerprint", table_name="reusable_sqls")
    op.drop_index("ix_reusable_sqls_datasource", table_name="reusable_sqls")
    op.drop_table("reusable_sqls")

    op.drop_index("ix_golden_sqls_datasource", table_name="golden_sqls")
    op.drop_table("golden_sqls")
    op.drop_table("llm_logs")

    with op.batch_alter_table("backup_records") as batch_op:
        batch_op.drop_column("environment_id")

    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.drop_index("ix_data_sources_environment_id")
        batch_op.drop_column("environment_id")

    op.drop_index("ix_database_environments_status", table_name="database_environments")
    op.drop_index("ix_database_environments_project", table_name="database_environments")
    op.drop_table("database_environments")


def downgrade() -> None:
    op.create_table(
        "database_environments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("runtime", sa.String(), nullable=False),
        sa.Column("engine_type", sa.String(), nullable=False),
        sa.Column("engine_version", sa.String(), nullable=False),
        sa.Column("image", sa.String(), nullable=False),
        sa.Column("container_name", sa.String(), nullable=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database_name", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("last_health_status", sa.String(), nullable=True),
        sa.Column("last_health_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("password_credential_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_database_environments_project",
        "database_environments",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_database_environments_status",
        "database_environments",
        ["status"],
        unique=False,
    )

    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.add_column(sa.Column("environment_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_data_sources_environment_id_database_environments",
            "database_environments",
            ["environment_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_data_sources_environment_id", ["environment_id"], unique=False)

    with op.batch_alter_table("backup_records") as batch_op:
        batch_op.add_column(sa.Column("environment_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_backup_records_environment_id_database_environments",
            "database_environments",
            ["environment_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "llm_logs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=True),
        sa.Column("request_type", sa.String(), nullable=False),
        sa.Column("prompt_hash", sa.String(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("prompt_template_hash", sa.String(), nullable=True),
        sa.Column("model_temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "golden_sqls",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("golden_sql", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "question", name="uq_golden_sqls_ds_question"),
    )
    op.create_index("ix_golden_sqls_datasource", "golden_sqls", ["data_source_id"], unique=False)

    op.create_table(
        "reusable_sqls",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("safe_sql", sa.Text(), nullable=False),
        sa.Column("sql_fingerprint", sa.String(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("involved_tables_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("result_columns_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("source_artifact_id", sa.String(), nullable=True),
        sa.Column("source_sql_artifact_id", sa.String(), nullable=True),
        sa.Column("usage_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id",
            "sql_fingerprint",
            name="uq_reusable_sqls_ds_fingerprint",
        ),
    )
    op.create_index("ix_reusable_sqls_datasource", "reusable_sqls", ["data_source_id"], unique=False)
    op.create_index("ix_reusable_sqls_fingerprint", "reusable_sqls", ["sql_fingerprint"], unique=False)

    op.create_table(
        "workspace_table_scopes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("data_source_id", sa.String(), nullable=False),
        sa.Column("table_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_sources.id"],
            name="fk_workspace_table_scopes_data_source_id_data_sources",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_workspace_table_scopes_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["table_id"],
            ["schema_tables.id"],
            name="fk_workspace_table_scopes_table_id_schema_tables",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "data_source_id",
            "table_id",
            name="uq_workspace_scopes_project_ds_table",
        ),
    )
    op.create_index(
        "ix_workspace_table_scopes_project_ds",
        "workspace_table_scopes",
        ["project_id", "data_source_id"],
        unique=False,
    )
