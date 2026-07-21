"""Database-only operations used by the two-phase Foundation runtime reset."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine


def read_marker(
    connection: Connection,
    *,
    runtime_version: str,
    upgradable_versions: frozenset[str],
    state_error: type[Exception],
) -> str:
    marker = connection.execute(
        text(
            "SELECT runtime_version, reset_completed_at "
            "FROM foundation_runtime_state WHERE id = 1"
        )
    ).mappings().one_or_none()
    if marker is None:
        return "missing"
    version = str(marker["runtime_version"])
    if version in upgradable_versions:
        return "legacy"
    if version != runtime_version:
        raise state_error()
    if marker["reset_completed_at"] is None:
        return "pending"
    return "completed"


def clear_database_runtime_state(
    connection: Connection,
    *,
    delete_order: Iterable[str],
) -> None:
    inspector = inspect(connection)
    for table_name in delete_order:
        if inspector.has_table(table_name):
            connection.execute(text(f"DELETE FROM {table_name}"))

    connection.execute(
        text(
            """
            UPDATE data_sources
            SET password_credential_id = NULL,
                ssh_password_credential_id = NULL,
                ssh_key_passphrase_credential_id = NULL,
                ssh_pkey_path = NULL,
                ssl_key_path = NULL,
                last_test_at = NULL,
                last_test_status = NULL,
                last_test_error = NULL,
                last_test_latency_ms = NULL,
                last_test_readonly = NULL,
                last_test_server_version = NULL,
                last_test_tables_count = NULL,
                last_test_warnings = NULL,
                last_sync_at = NULL,
                last_sync_status = NULL,
                last_sync_error = NULL,
                status = 'needs_credentials'
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE database_environments
            SET password_credential_id = NULL,
                status = 'created',
                last_health_status = NULL,
                last_health_at = NULL,
                last_error = NULL
            """
        )
    )
    connection.execute(text("INSERT INTO schema_search_fts(schema_search_fts) VALUES ('rebuild')"))
    connection.execute(text("INSERT INTO query_history_fts(query_history_fts) VALUES ('rebuild')"))


def write_pending_marker(connection: Connection, *, runtime_version: str) -> None:
    connection.execute(
        text(
            """
            INSERT INTO foundation_runtime_state (id, runtime_version, reset_completed_at)
            VALUES (:id, :runtime_version, :reset_completed_at)
            ON CONFLICT(id) DO UPDATE SET
                runtime_version = excluded.runtime_version,
                reset_completed_at = excluded.reset_completed_at
            """
        ),
        {"id": 1, "runtime_version": runtime_version, "reset_completed_at": None},
    )


def mark_cleanup_completed(connection: Connection, *, runtime_version: str) -> None:
    connection.execute(
        text(
            """
            UPDATE foundation_runtime_state
            SET reset_completed_at = :reset_completed_at
            WHERE id = 1 AND runtime_version = :runtime_version
            """
        ),
        {
            "runtime_version": runtime_version,
            "reset_completed_at": datetime.now(UTC).isoformat(),
        },
    )


def compact_metadata_after_reset(
    engine: Engine,
    *,
    cleanup_error: type[Exception],
) -> None:
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.exec_driver_sql("VACUUM")
            connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception as exc:
        raise cleanup_error() from exc
