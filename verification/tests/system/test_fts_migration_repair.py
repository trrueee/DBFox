from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, text


pytestmark = pytest.mark.migration


PRE_REPAIR_REVISION = "5a6b7c8d9e0f"
_TRIGGERS = {
    "query_history_search_docs_ai",
    "query_history_search_docs_ad",
    "query_history_search_docs_au",
}


def _config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "engine" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_fts_repair_history_converges_to_the_current_core_only_fts_contract(
    tmp_path: Path,
) -> None:
    metadata_path = tmp_path / "metadata.db"
    database_url = f"sqlite:///{metadata_path.as_posix()}"
    config = _config(database_url)
    command.upgrade(config, PRE_REPAIR_REVISION)

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP TRIGGER query_history_search_docs_au"))
            connection.execute(text("DROP TRIGGER query_history_search_docs_ad"))
            connection.execute(text("DROP TRIGGER query_history_search_docs_ai"))
            connection.execute(text("DROP TABLE query_history_fts"))
            connection.execute(text("DROP TABLE schema_search_fts"))
    finally:
        engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            objects = {
                row[0]
                for row in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')")
                )
            }
            assert "agent_message_fts" in objects
            assert {"schema_search_fts", "query_history_fts"}.isdisjoint(objects)
            assert _TRIGGERS.isdisjoint(objects)
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == ScriptDirectory.from_config(config).get_current_head()
            connection.execute(text("SELECT search_text FROM agent_message_fts LIMIT 0"))
    finally:
        engine.dispose()
