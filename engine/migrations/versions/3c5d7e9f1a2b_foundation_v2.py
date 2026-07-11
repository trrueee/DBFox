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

from collections.abc import Mapping
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
_FTS_CONTENT_TABLES = ("schema_search_docs", "query_history_search_docs")
_SQLITE_IDENTIFIER_ASCII_FOLD = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
)

_REQUIRED_V2_TABLE_COLUMNS = {
    "projects": {"id"},
    "data_sources": {"id", "project_id", "environment_id"},
    "database_environments": {"id", "project_id", "datasource_id"},
    "schema_tables": {"id", "data_source_id"},
    "schema_columns": {"id", "table_id", "foreign_table_id", "foreign_column_id"},
    "schema_search_docs": {"id", "search_text"},
    "query_history": {"id", "data_source_id"},
    "query_history_search_docs": {"id", "history_id", "search_text"},
    "agent_sessions": {"id"},
    "agent_runs": {"id", "session_id", "datasource_id"},
    "agent_approvals": {"id", "run_id", "session_id"},
    "workspace_table_scopes": {"id", "table_id"},
    "semantic_aliases": {"id", "data_source_id"},
}


def _has_table(bind: sa.Connection, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _column_names(bind: sa.Connection, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _column_name_lookup(bind: sa.Connection, table_name: str) -> dict[str, str]:
    column_names = _column_names(bind, table_name)
    if bind.dialect.name == "sqlite":
        return _table_name_lookup(column_names)
    return {column_name: column_name for column_name in column_names}


def _resolved_column_name(
    bind: sa.Connection,
    table_name: str,
    column_name: str,
) -> str | None:
    lookup = _column_name_lookup(bind, table_name)
    key = _sqlite_identifier_key(column_name) if bind.dialect.name == "sqlite" else column_name
    return lookup.get(key)


def _has_column(bind: sa.Connection, table_name: str, column_name: str) -> bool:
    return _resolved_column_name(bind, table_name, column_name) is not None


def _add_column_if_missing(bind: sa.Connection, table_name: str, column: sa.Column) -> None:
    if _has_table(bind, table_name) and not _has_column(bind, table_name, column.name):
        op.add_column(table_name, column)


def _drop_columns_if_present(bind: sa.Connection, table_name: str, column_names: set[str]) -> None:
    if not _has_table(bind, table_name):
        return
    for column_name in sorted(column_names):
        actual_column_name = _resolved_column_name(bind, table_name, column_name)
        if actual_column_name is not None:
            op.drop_column(table_name, actual_column_name)


def _sqlite_identifier_key(identifier: str) -> str:
    """Apply SQLite's ASCII-only identifier case folding."""
    return identifier.translate(_SQLITE_IDENTIFIER_ASCII_FOLD)


def _table_name_lookup(table_names: set[str]) -> dict[str, str]:
    """Map SQLite-equivalent identifiers to their reflected spelling."""
    return {_sqlite_identifier_key(table_name): table_name for table_name in table_names}


def _resolved_table_name(bind: sa.Connection, table_name: str) -> str | None:
    table_names = set(sa.inspect(bind).get_table_names())
    if bind.dialect.name == "sqlite":
        return _table_name_lookup(table_names).get(_sqlite_identifier_key(table_name))
    return table_name if table_name in table_names else None


def _identifiers_equivalent(bind: sa.Connection, left: str, right: str) -> bool:
    if bind.dialect.name == "sqlite":
        return _sqlite_identifier_key(left) == _sqlite_identifier_key(right)
    return left == right


def _validate_foreign_key_shape(
    *,
    table_name: str,
    columns: set[str],
    foreign_key: Mapping[str, object],
    table_lookup: dict[str, str],
    column_names_by_table: dict[str, set[str]],
) -> tuple[list[str], list[str], str | None]:
    local_columns_value = foreign_key.get("constrained_columns")
    referred_columns_value = foreign_key.get("referred_columns")
    referred_table = foreign_key.get("referred_table")
    if not isinstance(local_columns_value, list) or not isinstance(referred_columns_value, list):
        raise RuntimeError(
            "foundation v2 cannot repair malformed foreign key "
            f"on {table_name}: {foreign_key!r}"
        )
    local_columns = [column for column in local_columns_value if isinstance(column, str)]
    referred_columns = [
        column for column in referred_columns_value if isinstance(column, str)
    ]
    column_lookup = _table_name_lookup(columns)
    if (
        not local_columns
        or len(local_columns) != len(local_columns_value)
        or len(referred_columns) != len(referred_columns_value)
        or len(local_columns) != len(referred_columns)
        or not isinstance(referred_table, str)
        or any(_sqlite_identifier_key(column) not in column_lookup for column in local_columns)
    ):
        raise RuntimeError(
            "foundation v2 cannot repair malformed foreign key "
            f"on {table_name}: {foreign_key!r}"
        )

    resolved_local_columns = [
        column_lookup[_sqlite_identifier_key(column)] for column in local_columns
    ]
    resolved_referred_table = table_lookup.get(_sqlite_identifier_key(referred_table))
    if resolved_referred_table is None:
        # SQLite permits a child table to outlive its referred table.  Every
        # non-NULL child key is necessarily orphaned and is safely repaired
        # below without issuing a query against the absent parent.
        return resolved_local_columns, referred_columns, None

    referred_column_lookup = _table_name_lookup(
        column_names_by_table[resolved_referred_table]
    )
    if any(
        _sqlite_identifier_key(column) not in referred_column_lookup
        for column in referred_columns
    ):
        raise RuntimeError(
            "foundation v2 cannot repair malformed foreign key "
            f"on {table_name}: {foreign_key!r}"
        )
    return (
        resolved_local_columns,
        [referred_column_lookup[_sqlite_identifier_key(column)] for column in referred_columns],
        resolved_referred_table,
    )


def _preflight_v2_schema(bind: sa.Connection) -> None:
    """Validate every live-schema prerequisite before v2 changes any state."""
    if bind.dialect.name != "sqlite":
        return

    try:
        bind.exec_driver_sql("SELECT fts5_source_id()").scalar_one()
    except sa.exc.DBAPIError as exc:
        raise RuntimeError("foundation v2 requires SQLite FTS5 support") from exc

    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    table_lookup = _table_name_lookup(table_names)
    missing_content_tables = sorted(
        table_name
        for table_name in _FTS_CONTENT_TABLES
        if _sqlite_identifier_key(table_name) not in table_lookup
    )
    if missing_content_tables:
        raise RuntimeError(
            "foundation v2 FTS content tables are missing: " + ", ".join(missing_content_tables)
        )

    missing_tables = sorted(
        table_name
        for table_name in _REQUIRED_V2_TABLE_COLUMNS
        if _sqlite_identifier_key(table_name) not in table_lookup
    )
    if missing_tables:
        raise RuntimeError(
            "foundation v2 required tables are missing: " + ", ".join(missing_tables)
        )

    column_names_by_table = {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in table_names
    }
    for expected_table_name, required_columns in _REQUIRED_V2_TABLE_COLUMNS.items():
        table_name = table_lookup[_sqlite_identifier_key(expected_table_name)]
        column_lookup = _table_name_lookup(column_names_by_table[table_name])
        missing_columns = sorted(
            column_name
            for column_name in required_columns
            if _sqlite_identifier_key(column_name) not in column_lookup
        )
        if missing_columns:
            raise RuntimeError(
                f"foundation v2 required columns are missing from {table_name}: "
                + ", ".join(missing_columns)
            )

    # Repair runs across the complete live schema, not only DBFox-owned
    # tables.  Reject malformed *repair plans* here, before the first v2 DDL
    # or SQLite autocommit block.  An absent parent table is intentionally
    # allowed: the repair pass NULLs/deletes every non-NULL child reference.
    for table_name in sorted(table_names):
        columns = column_names_by_table[table_name]
        for foreign_key in inspector.get_foreign_keys(table_name):
            _validate_foreign_key_shape(
                table_name=table_name,
                columns=columns,
                foreign_key=foreign_key,
                table_lookup=table_lookup,
                column_names_by_table=column_names_by_table,
            )

    # This read-only pragma catches invalid parent-key configurations that
    # SQLite's inspector cannot represent (for example, a non-unique parent
    # target). Ordinary orphan rows are returned, not raised, and are repaired
    # after FK enforcement is disabled.
    try:
        bind.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    except sa.exc.DBAPIError as exc:
        raise RuntimeError("foundation v2 cannot repair invalid foreign key configuration") from exc


def _has_expected_fk(
    bind: sa.Connection,
    table_name: str,
    column_name: str,
    referred_table: str,
    ondelete: str,
) -> bool:
    return any(
        len(fk["constrained_columns"]) == 1
        and _identifiers_equivalent(bind, fk["constrained_columns"][0], column_name)
        and _identifiers_equivalent(bind, fk["referred_table"], referred_table)
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
    actual_table_name = _resolved_table_name(bind, table_name)
    actual_referred_table = _resolved_table_name(bind, referred_table)
    if actual_table_name is None or actual_referred_table is None:
        return
    actual_column_name = _resolved_column_name(bind, actual_table_name, column_name)
    actual_referred_column = _resolved_column_name(bind, actual_referred_table, "id")
    if actual_column_name is None or actual_referred_column is None:
        return
    if _has_expected_fk(
        bind,
        actual_table_name,
        actual_column_name,
        actual_referred_table,
        ondelete,
    ):
        return

    foreign_keys = [
        fk
        for fk in sa.inspect(bind).get_foreign_keys(actual_table_name)
        if len(fk["constrained_columns"]) == 1
        and _identifiers_equivalent(bind, fk["constrained_columns"][0], actual_column_name)
    ]
    constraint_name = f"fk_{table_name}_{column_name}_{referred_table}"

    with op.batch_alter_table(
        actual_table_name,
        recreate="always",
        naming_convention=_SQLITE_FK_NAMING_CONVENTION,
    ) as batch_op:
        for foreign_key in foreign_keys:
            existing_name = foreign_key.get("name") or constraint_name
            batch_op.drop_constraint(existing_name, type_="foreignkey")
        batch_op.create_foreign_key(
            constraint_name,
            actual_referred_table,
            [actual_column_name],
            [actual_referred_column],
            ondelete=ondelete,
        )


def _clear_invalid_catalog_references(bind: sa.Connection) -> None:
    if _has_table(bind, "schema_columns"):
        if _has_column(bind, "schema_columns", "foreign_table_id") and _has_table(
            bind, "schema_tables"
        ):
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
        if _has_column(bind, "schema_columns", "foreign_column_id"):
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


def _usable_sqlite_rowid(
    bind: sa.Connection,
    child_table: str,
    column_names: set[str],
) -> str | None:
    """Return an unshadowed rowid alias, or None for WITHOUT ROWID tables."""
    column_keys = {_sqlite_identifier_key(column) for column in column_names}
    for candidate in ("rowid", "_rowid_", "oid"):
        if _sqlite_identifier_key(candidate) in column_keys:
            continue
        try:
            bind.execute(sa.text(f"SELECT {candidate} FROM {child_table} LIMIT 0"))
        except sa.exc.DBAPIError:
            continue
        return candidate
    return None


def _repair_nullable_orphans_or_delete(
    bind: sa.Connection,
    *,
    inspector: sa.Inspector,
    table_name: str,
    child_table: str,
    assignments: str,
    invalid_predicate: str,
) -> int:
    """Try per-row NULL repair; delete only rows blocked by DB constraints."""
    primary_key_columns = list(
        inspector.get_pk_constraint(table_name).get("constrained_columns") or []
    )
    column_names = {
        column["name"] for column in inspector.get_columns(table_name)
    }
    rowid_column = _usable_sqlite_rowid(bind, child_table, column_names)
    if rowid_column is None and not primary_key_columns:
        bind.execute(sa.text(f"DELETE FROM {child_table} WHERE {invalid_predicate}"))
        return int(bind.exec_driver_sql("SELECT changes()").scalar_one())

    preparer = bind.dialect.identifier_preparer
    if rowid_column is not None:
        rows = bind.execute(
            sa.text(
                f"SELECT {rowid_column} AS _dbfox_rowid "
                f"FROM {child_table} WHERE {invalid_predicate}"
            )
        ).mappings().all()
        identities = [
            (f"{rowid_column} = :rowid", {"rowid": row["_dbfox_rowid"]})
            for row in rows
        ]
    else:
        selected_columns = ", ".join(
            preparer.quote(column) for column in primary_key_columns
        )
        rows = bind.execute(
            sa.text(f"SELECT {selected_columns} FROM {child_table} WHERE {invalid_predicate}")
        ).mappings().all()
        if any(
            row[column_name] is None
            for row in rows
            for column_name in primary_key_columns
        ):
            # A rowid alias was unavailable and SQLite permits NULLs in a
            # rowid-table composite primary key.  A PK predicate could match
            # multiple rows, so delete only currently invalid rows instead.
            bind.execute(sa.text(f"DELETE FROM {child_table} WHERE {invalid_predicate}"))
            return int(bind.exec_driver_sql("SELECT changes()").scalar_one())
        identities = []
        for row in rows:
            identity_parts: list[str] = []
            params: dict[str, object] = {}
            for index, column_name in enumerate(primary_key_columns):
                parameter_name = f"identity_{index}"
                identity_parts.append(
                    f"{preparer.quote(column_name)} = :{parameter_name}"
                )
                params[parameter_name] = row[column_name]
            identities.append((" AND ".join(identity_parts), params))

    changed = 0
    for identity_predicate, params in identities:
        try:
            with bind.begin_nested():
                bind.execute(
                    sa.text(f"UPDATE {child_table} SET {assignments} WHERE {identity_predicate}"),
                    params,
                )
        except sa.exc.IntegrityError:
            bind.execute(
                sa.text(f"DELETE FROM {child_table} WHERE {identity_predicate}"),
                params,
            )
        changed += int(bind.exec_driver_sql("SELECT changes()").scalar_one())
    return changed


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
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    table_lookup = _table_name_lookup(table_names)
    nullable_columns_by_table = {
        table_name: {
            column["name"]: bool(column.get("nullable", False))
            for column in inspector.get_columns(table_name)
        }
        for table_name in table_names
    }
    column_names_by_table = {
        table_name: set(columns) for table_name, columns in nullable_columns_by_table.items()
    }

    while True:
        changed = False
        for table_name in sorted(table_names):
            columns = nullable_columns_by_table[table_name]
            child_table = preparer.quote(table_name)
            for foreign_key in inspector.get_foreign_keys(table_name):
                local_columns, referred_columns, referred_table = _validate_foreign_key_shape(
                    table_name=table_name,
                    columns=set(columns),
                    foreign_key=foreign_key,
                    table_lookup=table_lookup,
                    column_names_by_table=column_names_by_table,
                )

                child_columns = [f"{child_table}.{preparer.quote(column)}" for column in local_columns]
                not_null = " AND ".join(f"{column} IS NOT NULL" for column in child_columns)
                if referred_table is None:
                    invalid_predicate = not_null
                else:
                    parent_table = preparer.quote(referred_table)
                    matches = " AND ".join(
                        f"parent.{preparer.quote(parent_column)} = {child_column}"
                        for parent_column, child_column in zip(referred_columns, child_columns)
                    )
                    invalid_predicate = (
                        f"{not_null} AND NOT EXISTS "
                        f"(SELECT 1 FROM {parent_table} AS parent WHERE {matches})"
                    )

                nullable_columns = [column for column in local_columns if columns[column]]
                if nullable_columns:
                    assignments = ", ".join(
                        f"{preparer.quote(column)} = NULL" for column in nullable_columns
                    )
                    repaired = _repair_nullable_orphans_or_delete(
                        bind,
                        inspector=inspector,
                        table_name=table_name,
                        child_table=child_table,
                        assignments=assignments,
                        invalid_predicate=invalid_predicate,
                    )
                else:
                    bind.execute(
                        sa.text(f"DELETE FROM {child_table} WHERE {invalid_predicate}")
                    )
                    repaired = int(bind.exec_driver_sql("SELECT changes()").scalar_one())
                if repaired > 0:
                    changed = True
        if not changed:
            violations = bind.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(
                    "foundation v2 could not repair legacy foreign key violations: "
                    f"{violations!r}"
                )
            return


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

    _preflight_v2_schema(bind)

    # env.py disables SQLite enforcement for the complete Alembic transaction,
    # including the version-table stamp.  This batch recreation creates a
    # temporary self-reference to the old table name.
    _upgrade_to_foundation_v2(bind)
    _assert_sqlite_foreign_keys_clean(bind)


def downgrade() -> None:
    raise NotImplementedError(
        "foundation v2 intentionally destroys legacy secret metadata and cannot be downgraded safely"
    )
