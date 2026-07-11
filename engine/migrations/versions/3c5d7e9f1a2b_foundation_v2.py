"""establish the foundation v2 metadata schema contract

Revision ID: 3c5d7e9f1a2b
Revises: 2b4c6d8e0f12
Create Date: 2026-07-11

The foundation v2 reset intentionally has no compatibility readers or dual
writes.  This revision removes legacy encrypted metadata fields and brings
both the canonical 2b schema and historical ``Base.create_all(); stamp 2b``
installations to the same final ORM contract.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3c5d7e9f1a2b"
down_revision: Union[str, Sequence[str], None] = "2b4c6d8e0f12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SQLITE_FK_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}

_LEGACY_DATASOURCE_SECRET_COLUMNS = {
    "password_ciphertext",
    "password_nonce",
    "password_key_version",
    "ssh_password_ciphertext",
    "ssh_password_nonce",
    "ssh_pkey_passphrase_ciphertext",
    "ssh_pkey_passphrase_nonce",
}

_SCHEMA_SEARCH_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS schema_search_fts
USING fts5(search_text, content='schema_search_docs', content_rowid='id')
"""

_QUERY_HISTORY_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS query_history_fts
USING fts5(search_text, content='query_history_search_docs', content_rowid='id')
"""

_QUERY_HISTORY_FTS_TRIGGERS = (
    """
    CREATE TRIGGER IF NOT EXISTS query_history_search_docs_ai
    AFTER INSERT ON query_history_search_docs BEGIN
        INSERT INTO query_history_fts(rowid, search_text)
        VALUES (new.id, new.search_text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS query_history_search_docs_ad
    AFTER DELETE ON query_history_search_docs BEGIN
        INSERT INTO query_history_fts(query_history_fts, rowid, search_text)
        VALUES ('delete', old.id, old.search_text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS query_history_search_docs_au
    AFTER UPDATE ON query_history_search_docs BEGIN
        INSERT INTO query_history_fts(query_history_fts, rowid, search_text)
        VALUES ('delete', old.id, old.search_text);
        INSERT INTO query_history_fts(rowid, search_text)
        VALUES (new.id, new.search_text);
    END
    """,
)

_FTS_SHADOW_SUFFIXES = ("data", "idx", "content", "docsize", "config")


def _has_table(bind: sa.Connection, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _column_names(bind: sa.Connection, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _add_column_if_missing(bind: sa.Connection, table_name: str, column: sa.Column) -> None:
    if _has_table(bind, table_name) and column.name not in _column_names(bind, table_name):
        op.add_column(table_name, column)


def _drop_columns_if_present(bind: sa.Connection, table_name: str, column_names: set[str]) -> None:
    if not _has_table(bind, table_name):
        return
    for column_name in sorted(column_names & _column_names(bind, table_name)):
        op.drop_column(table_name, column_name)


def _has_expected_fk(
    bind: sa.Connection,
    table_name: str,
    column_name: str,
    referred_table: str,
    ondelete: str,
) -> bool:
    return any(
        fk["constrained_columns"] == [column_name]
        and fk["referred_table"] == referred_table
        and str(fk.get("options", {}).get("ondelete", "")).upper() == ondelete
        for fk in sa.inspect(bind).get_foreign_keys(table_name)
    )


def _ensure_foreign_key(
    bind: sa.Connection,
    table_name: str,
    column_name: str,
    referred_table: str,
    ondelete: str,
) -> None:
    """Add or replace a one-column FK, including unnamed SQLite constraints."""
    if not _has_table(bind, table_name) or not _has_table(bind, referred_table):
        return
    if _has_expected_fk(bind, table_name, column_name, referred_table, ondelete):
        return

    foreign_keys = [
        fk
        for fk in sa.inspect(bind).get_foreign_keys(table_name)
        if fk["constrained_columns"] == [column_name]
    ]
    constraint_name = f"fk_{table_name}_{column_name}_{referred_table}"

    with op.batch_alter_table(
        table_name,
        recreate="always",
        naming_convention=_SQLITE_FK_NAMING_CONVENTION,
    ) as batch_op:
        for foreign_key in foreign_keys:
            existing_name = foreign_key.get("name") or constraint_name
            batch_op.drop_constraint(existing_name, type_="foreignkey")
        batch_op.create_foreign_key(
            constraint_name,
            referred_table,
            [column_name],
            ["id"],
            ondelete=ondelete,
        )


def _clear_invalid_catalog_references(bind: sa.Connection) -> None:
    if _has_table(bind, "schema_columns"):
        columns = _column_names(bind, "schema_columns")
        if "foreign_table_id" in columns and _has_table(bind, "schema_tables"):
            bind.execute(
                sa.text(
                    """
                    UPDATE schema_columns
                    SET foreign_table_id = NULL
                    WHERE foreign_table_id IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM schema_tables
                          WHERE schema_tables.id = schema_columns.foreign_table_id
                      )
                    """
                )
            )
        if "foreign_column_id" in columns:
            bind.execute(
                sa.text(
                    """
                    UPDATE schema_columns
                    SET foreign_column_id = NULL
                    WHERE foreign_column_id IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM schema_columns AS referenced_column
                          WHERE referenced_column.id = schema_columns.foreign_column_id
                      )
                    """
                )
            )

    if _has_table(bind, "agent_approvals") and _has_table(bind, "agent_sessions"):
        bind.execute(
            sa.text(
                """
                DELETE FROM agent_approvals
                WHERE NOT EXISTS (
                    SELECT 1 FROM agent_sessions
                    WHERE agent_sessions.id = agent_approvals.session_id
                )
                """
            )
        )

    if _has_table(bind, "workspace_table_scopes") and _has_table(bind, "schema_tables"):
        bind.execute(
            sa.text(
                """
                DELETE FROM workspace_table_scopes
                WHERE NOT EXISTS (
                    SELECT 1 FROM schema_tables
                    WHERE schema_tables.id = workspace_table_scopes.table_id
                )
                """
            )
        )


def _repair_legacy_orphan_foreign_keys(bind: sa.Connection) -> None:
    """Repair every reflected FK while enforcement is off for the v2 upgrade.

    Legacy metadata could be written while SQLite FK enforcement was disabled.
    Nullable child keys retain their rows and are set to NULL; a row whose
    invalid FK cannot be NULL is removed.  Repeating the pass handles chains
    where deleting one invalid child makes another self/reference row invalid.
    """
    if bind.dialect.name != "sqlite":
        return

    preparer = bind.dialect.identifier_preparer
    table_names = set(sa.inspect(bind).get_table_names())

    while True:
        changed = False
        inspector = sa.inspect(bind)
        for table_name in sorted(table_names):
            columns = {
                column["name"]: bool(column.get("nullable", False))
                for column in inspector.get_columns(table_name)
            }
            child_table = preparer.quote(table_name)
            for foreign_key in inspector.get_foreign_keys(table_name):
                local_columns = list(foreign_key.get("constrained_columns") or [])
                referred_columns = list(foreign_key.get("referred_columns") or [])
                referred_table = foreign_key.get("referred_table")
                if (
                    not local_columns
                    or len(local_columns) != len(referred_columns)
                    or not isinstance(referred_table, str)
                    or any(not isinstance(column, str) for column in local_columns)
                    or any(not isinstance(column, str) for column in referred_columns)
                    or any(column not in columns for column in local_columns)
                ):
                    raise RuntimeError(
                        "foundation v2 cannot repair malformed foreign key "
                        f"on {table_name}: {foreign_key!r}"
                    )

                child_columns = [f"{child_table}.{preparer.quote(column)}" for column in local_columns]
                not_null = " AND ".join(f"{column} IS NOT NULL" for column in child_columns)
                if referred_table in table_names:
                    parent_table = preparer.quote(referred_table)
                    matches = " AND ".join(
                        f"parent.{preparer.quote(parent_column)} = {child_column}"
                        for parent_column, child_column in zip(referred_columns, child_columns)
                    )
                    invalid_predicate = (
                        f"{not_null} AND NOT EXISTS "
                        f"(SELECT 1 FROM {parent_table} AS parent WHERE {matches})"
                    )
                else:
                    invalid_predicate = not_null

                nullable_columns = [column for column in local_columns if columns[column]]
                if nullable_columns:
                    assignments = ", ".join(
                        f"{preparer.quote(column)} = NULL" for column in nullable_columns
                    )
                    bind.execute(
                        sa.text(f"UPDATE {child_table} SET {assignments} WHERE {invalid_predicate}")
                    )
                else:
                    bind.execute(
                        sa.text(f"DELETE FROM {child_table} WHERE {invalid_predicate}")
                    )
                if bind.exec_driver_sql("SELECT changes()").scalar_one() > 0:
                    changed = True
        if not changed:
            violations = bind.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(
                    "foundation v2 could not repair legacy foreign key violations: "
                    f"{violations!r}"
                )
            return


def _set_sqlite_foreign_keys(bind: sa.Connection, enabled: bool) -> None:
    """Toggle enforcement outside a transaction for SQLite batch recreation."""
    if bind.dialect.name == "sqlite":
        with op.get_context().autocommit_block():
            bind.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


def _assert_sqlite_foreign_keys_clean(bind: sa.Connection) -> None:
    if bind.dialect.name != "sqlite":
        return
    violations = bind.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"foundation v2 migration left foreign key violations: {violations!r}")


def _create_runtime_state_table(bind: sa.Connection) -> None:
    if _has_table(bind, "foundation_runtime_state"):
        return
    op.create_table(
        "foundation_runtime_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("runtime_version", sa.String(), nullable=False),
        sa.Column("reset_completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_foundation_runtime_state_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )


def _ensure_fts_contract(bind: sa.Connection) -> None:
    """Make FTS virtual tables and query-history synchronization migration-owned."""
    if bind.dialect.name != "sqlite":
        return

    required_content_tables = {"schema_search_docs", "query_history_search_docs"}
    missing_content_tables = sorted(
        table_name for table_name in required_content_tables if not _has_table(bind, table_name)
    )
    if missing_content_tables:
        raise RuntimeError(
            "foundation v2 FTS content tables are missing: " + ", ".join(missing_content_tables)
        )

    for trigger_name in (
        "query_history_search_docs_ai",
        "query_history_search_docs_ad",
        "query_history_search_docs_au",
    ):
        bind.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
    for virtual_table in ("schema_search_fts", "query_history_fts"):
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {virtual_table}"))
        for suffix in _FTS_SHADOW_SUFFIXES:
            bind.execute(sa.text(f"DROP TABLE IF EXISTS {virtual_table}_{suffix}"))

    bind.execute(sa.text(_SCHEMA_SEARCH_FTS_DDL))
    bind.execute(sa.text(_QUERY_HISTORY_FTS_DDL))
    for trigger in _QUERY_HISTORY_FTS_TRIGGERS:
        bind.execute(sa.text(trigger))
    bind.execute(sa.text("INSERT INTO schema_search_fts(schema_search_fts) VALUES ('rebuild')"))
    bind.execute(sa.text("INSERT INTO query_history_fts(query_history_fts) VALUES ('rebuild')"))


def _upgrade_to_foundation_v2(bind: sa.Connection) -> None:
    # The retired semantic models are not part of the v2 metadata contract.
    # Drop their child tables before changing the datasource contract they
    # reference, so SQLite can retain foreign-key enforcement for normal work.
    for table_name in ("semantic_dimensions", "semantic_metrics"):
        if _has_table(bind, table_name):
            op.drop_table(table_name)

    _drop_columns_if_present(
        bind,
        "semantic_aliases",
        {"embedding_blob", "embedding_synced_at"},
    )

    for credential_column in (
        sa.Column("password_credential_id", sa.String(), nullable=True),
        sa.Column("ssh_password_credential_id", sa.String(), nullable=True),
        sa.Column("ssh_key_passphrase_credential_id", sa.String(), nullable=True),
    ):
        _add_column_if_missing(bind, "data_sources", credential_column)
    _drop_columns_if_present(
        bind,
        "data_sources",
        _LEGACY_DATASOURCE_SECRET_COLUMNS | {"enable_embedding_recall"},
    )

    _add_column_if_missing(
        bind,
        "database_environments",
        sa.Column("password_credential_id", sa.String(), nullable=True),
    )
    _drop_columns_if_present(
        bind,
        "database_environments",
        {"password_ciphertext", "password_nonce", "password_key_version"},
    )

    for llm_column in (
        sa.Column("llm_credential_id", sa.String(), nullable=True),
        sa.Column("api_base", sa.String(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=True),
    ):
        _add_column_if_missing(bind, "agent_runs", llm_column)

    _clear_invalid_catalog_references(bind)

    _ensure_foreign_key(
        bind,
        "schema_columns",
        "foreign_table_id",
        "schema_tables",
        "SET NULL",
    )
    _ensure_foreign_key(
        bind,
        "schema_columns",
        "foreign_column_id",
        "schema_columns",
        "SET NULL",
    )
    _ensure_foreign_key(
        bind,
        "agent_approvals",
        "session_id",
        "agent_sessions",
        "CASCADE",
    )
    _ensure_foreign_key(
        bind,
        "workspace_table_scopes",
        "table_id",
        "schema_tables",
        "CASCADE",
    )

    _create_runtime_state_table(bind)
    _repair_legacy_orphan_foreign_keys(bind)
    _ensure_fts_contract(bind)


def upgrade() -> None:
    bind = op.get_bind()

    # A batch recreation of schema_columns creates a temporary self-reference
    # to the old table name.  SQLite must have enforcement disabled before any
    # migration DML begins or dropping the old table SET NULLs copied values.
    _set_sqlite_foreign_keys(bind, False)
    try:
        _upgrade_to_foundation_v2(bind)
    finally:
        _set_sqlite_foreign_keys(bind, True)
    _assert_sqlite_foreign_keys_clean(bind)


def downgrade() -> None:
    raise NotImplementedError(
        "foundation v2 intentionally destroys legacy secret metadata and cannot be downgraded safely"
    )
