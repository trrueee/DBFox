"""Cut legacy Core Data state over to the dbfox.data System DLC.

Revision ID: e2f3a4b5c6d8
Revises: d1e2f3a4b5c7

Connection identities and opaque credential references are copied and verified
before the old tables are removed. Catalog/search/history rows are derived or
superseded state and are rebuilt by dbfox.data after cutover.
"""

from collections.abc import Sequence

from alembic import op

from engine.migrations.data_dlc_state import migrate_legacy_data_sources


revision: str = "e2f3a4b5c6d8"
down_revision: str | None = "d1e2f3a4b5c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    migrate_legacy_data_sources(op.get_bind())

    op.execute("DROP TABLE IF EXISTS schema_search_fts")
    op.execute("DROP TABLE IF EXISTS query_history_fts")

    # Children first: SQLite's migration environment verifies the complete FK
    # graph before committing this irreversible domain-state cutover.
    for table_name in (
        "query_history_search_docs",
        "schema_search_docs",
        "schema_columns",
        "restore_operations",
        "backup_records",
        "query_history",
        "semantic_aliases",
        "domain_tag_rules",
        "schema_tables",
        "confirmation_tokens",
        "data_sources",
    ):
        op.drop_table(table_name)


def downgrade() -> None:
    raise RuntimeError(
        "Data DLC cutover is irreversible; restore the pre-migration SQLite snapshot"
    )
