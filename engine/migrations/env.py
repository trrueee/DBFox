from dataclasses import dataclass
from logging.config import fileConfig
import sqlite3
import sys
from pathlib import Path

# Add project root to sys.path so we can import engine modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from alembic import context
from alembic.util import CommandError
import sqlalchemy as sa

# Import our custom database engine builder and Base model.
from engine.db import Base, DATABASE_URL, build_metadata_engine
from engine.migrations.sqlite_mutex import sqlite_file_target, sqlite_migration_mutex
# Import models to ensure they are registered on Base.metadata for autogenerate
from engine import models

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    # Preserve application audit loggers created before Alembic runs during
    # FastAPI startup.  The logging.config default would disable every
    # unnamed ``dbfox.*`` logger and silently remove our error-boundary logs.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Set target metadata for autogenerate support
target_metadata = Base.metadata

_FTS_VIRTUAL_TABLES = {"schema_search_fts", "query_history_fts"}
_FTS_SHADOW_SUFFIXES = {"data", "idx", "content", "docsize", "config"}
_DEFAULT_ALEMBIC_URL = "driver://user:pass@localhost/dbname"
_OFFLINE_MIGRATION_ERROR = (
    "DBFOX_ALEMBIC_OFFLINE_UNSUPPORTED: metadata migrations require a live database connection; "
    "run 'alembic upgrade head' without --sql."
)


@dataclass
class _SQLiteFileSnapshot:
    """A disposable in-memory copy used to recover a file-backed SQLite DB."""

    database: str
    uri: bool
    connection: sqlite3.Connection


def _migration_url() -> str:
    """Use an explicit Alembic URL, with the stock ini value as a fallback."""
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url == _DEFAULT_ALEMBIC_URL:
        return DATABASE_URL
    return configured_url or DATABASE_URL


def _is_fts_table(name: str | None) -> bool:
    if name is None:
        return False
    return name in _FTS_VIRTUAL_TABLES or any(
        name == f"{virtual_table}_{suffix}"
        for virtual_table in _FTS_VIRTUAL_TABLES
        for suffix in _FTS_SHADOW_SUFFIXES
    )


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Keep SQLite FTS virtual tables and their shadow tables out of diffs."""
    if type_ == "table" and _is_fts_table(name):
        return False
    return True


def _set_sqlite_foreign_keys(connection: sa.Connection, enabled: bool) -> None:
    """Toggle SQLite FK enforcement outside the migration transaction."""
    if connection.in_transaction():
        connection.commit()
    connection.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")
    if connection.in_transaction():
        connection.commit()
    actual = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
    if bool(actual) is not enabled:
        raise RuntimeError(
            "DBFOX_ALEMBIC_SQLITE_FK_TOGGLE_FAILED: "
            f"expected foreign_keys={'ON' if enabled else 'OFF'}"
        )
    if connection.in_transaction():
        connection.commit()


def _assert_sqlite_foreign_keys_clean(connection: sa.Connection) -> None:
    violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(
            "DBFOX_ALEMBIC_SQLITE_FOREIGN_KEY_VIOLATIONS: " f"{violations!r}"
        )


def _take_sqlite_file_snapshot(
    database_url: str,
) -> _SQLiteFileSnapshot | None:
    """Copy a write-locked persistent metadata DB into memory."""
    target = sqlite_file_target(database_url)
    if target is None:
        return None

    source = sqlite3.connect(target[0], uri=target[1])
    snapshot_connection = sqlite3.connect(":memory:")
    try:
        source.backup(snapshot_connection)
    except BaseException:
        snapshot_connection.close()
        raise
    finally:
        source.close()
    return _SQLiteFileSnapshot(
        database=target[0],
        uri=target[1],
        connection=snapshot_connection,
    )


def _restore_sqlite_file_snapshot(snapshot: _SQLiteFileSnapshot) -> None:
    """Restore the pre-migration image after the migration engine is closed."""
    destination = sqlite3.connect(snapshot.database, uri=snapshot.uri)
    try:
        snapshot.connection.backup(destination)
    finally:
        destination.close()


def _close_sqlite_file_snapshot(snapshot: _SQLiteFileSnapshot | None) -> None:
    if snapshot is not None:
        snapshot.connection.close()


def run_migrations_offline() -> None:
    """Fail closed: v2 migration decisions require reflected live schema."""
    raise CommandError(_OFFLINE_MIGRATION_ERROR)


def _run_migrations_online(migration_url: str) -> None:
    """Run a single online migration while the DBFox SQLite mutex is held."""
    connectable = build_metadata_engine(migration_url)
    sqlite_snapshot: _SQLiteFileSnapshot | None = None
    try:
        with connectable.connect() as connection:
            is_sqlite = connection.dialect.name == "sqlite"
            try:
                if is_sqlite:
                    # SQLite cannot toggle this PRAGMA inside a transaction.
                    # Disable it before acquiring the write lock that covers
                    # both the snapshot and the full Alembic transaction.
                    _set_sqlite_foreign_keys(connection, False)
                    # sqlite3's implicit transaction mode does not begin a
                    # real transaction before DDL.  Force one now so table
                    # rebuilds and the Alembic version stamp commit or roll
                    # back together.  Alembic sees this as an external
                    # transaction and leaves its lifetime to this env script.
                    connection.exec_driver_sql("BEGIN IMMEDIATE")
                    # A separate read connection can back up the locked,
                    # pre-migration state without deadlocking the write
                    # connection.  No concurrent writer can commit between
                    # this image and the migration's first DDL.
                    sqlite_snapshot = _take_sqlite_file_snapshot(migration_url)

                configure_options = {
                    "connection": connection,
                    "target_metadata": target_metadata,
                    "render_as_batch": True,
                    "include_object": include_object,
                }
                if is_sqlite:
                    configure_options["transactional_ddl"] = True

                context.configure(**configure_options)
                with context.begin_transaction():
                    context.run_migrations()
                if is_sqlite:
                    # The revision validates before Alembic stamps its
                    # version.  Validate once more after that stamp, while
                    # the real transaction is still open, so a version-table
                    # trigger cannot leave a committed orphan behind.
                    _assert_sqlite_foreign_keys_clean(connection)
                    connection.commit()
            except BaseException:
                if is_sqlite:
                    # Alembic uses the explicit transaction above as an
                    # external transaction, so env.py owns the rollback.
                    connection.rollback()
                raise
            else:
                if is_sqlite:
                    _set_sqlite_foreign_keys(connection, True)
                    try:
                        _assert_sqlite_foreign_keys_clean(connection)
                    finally:
                        if connection.in_transaction():
                            connection.rollback()
    except BaseException:
        try:
            connectable.dispose()
        except BaseException:
            # The connection context has already closed.  Recovery of the
            # original metadata file is more important than a pool teardown
            # error, so continue with the in-memory image.
            pass
        try:
            if sqlite_snapshot is not None:
                _restore_sqlite_file_snapshot(sqlite_snapshot)
        except BaseException as restore_error:
            raise RuntimeError("DBFOX_ALEMBIC_SQLITE_SNAPSHOT_RESTORE_FAILED") from restore_error
        finally:
            _close_sqlite_file_snapshot(sqlite_snapshot)
        raise
    else:
        try:
            connectable.dispose()
        finally:
            _close_sqlite_file_snapshot(sqlite_snapshot)


def run_migrations_online() -> None:
    """Run migrations in online mode with a cross-process SQLite mutex."""
    # This lock is held across snapshot, DDL, Alembic version stamping, and
    # rollback/restore.  It serializes DBFox startup and CLI migrations for a
    # shared metadata file; BEGIN IMMEDIATE below still protects against raw
    # SQLite writers while an actual migration is active.
    migration_url = _migration_url()
    with sqlite_migration_mutex(migration_url):
        _run_migrations_online(migration_url)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
