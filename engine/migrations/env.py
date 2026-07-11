from logging.config import fileConfig
import sys
from pathlib import Path

# Add project root to sys.path so we can import engine modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from alembic import context

# Import our custom database engine builder and Base model.
from engine.db import Base, DATABASE_URL, build_metadata_engine
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


def _migration_url() -> str:
    """Use an explicit Alembic URL, with the stock ini value as a fallback."""
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url == _DEFAULT_ALEMBIC_URL:
        return DATABASE_URL
    return configured_url


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

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = _migration_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite requires batch mode for clean schema modifications
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Honor the URL supplied by this Alembic invocation.  Tests, maintenance
    # tooling, and init_db() can each target a different metadata file.
    connectable = build_metadata_engine(_migration_url())
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,  # SQLite batch mode to bypass drop/alter column limitations
                include_object=include_object,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
