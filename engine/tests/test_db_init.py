from __future__ import annotations

import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, text

from engine.db import Base

ALEMBIC_HEAD = "2b4c6d8e0f12"


def test_init_db_raises_when_alembic_upgrade_fails(monkeypatch, tmp_path) -> None:
    import alembic.command
    import engine.db as db_module

    metadata_path = tmp_path / "dbfox_metadata.db"
    database_url = f"sqlite:///{metadata_path}"
    test_engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with test_engine.begin() as conn:
        conn.execute(text("CREATE TABLE existing_table (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('99b4fdab0781')"))

    def fail_upgrade(*_args, **_kwargs) -> None:
        raise RuntimeError("forced migration failure")

    monkeypatch.setattr(db_module, "DB_PATH", metadata_path)
    monkeypatch.setattr(db_module, "DATABASE_URL", database_url)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(alembic.command, "upgrade", fail_upgrade)

    with pytest.raises(RuntimeError, match="forced migration failure"):
        db_module.init_db()


def test_init_db_stamps_existing_current_schema_without_alembic_version(monkeypatch, tmp_path) -> None:
    import engine.db as db_module

    metadata_path = tmp_path / "dbfox_existing_current_schema.db"
    database_url = f"sqlite:///{metadata_path}"
    test_engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)

    monkeypatch.setattr(db_module, "DB_PATH", metadata_path)
    monkeypatch.setattr(db_module, "DATABASE_URL", database_url)
    monkeypatch.setattr(db_module, "engine", test_engine)

    db_module.init_db()

    with test_engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert version == ALEMBIC_HEAD


def test_init_db_upgrades_legacy_d1_schema_without_alembic_version(monkeypatch, tmp_path) -> None:
    import engine.db as db_module

    metadata_path = tmp_path / "dbfox_legacy_d1_schema.db"
    database_url = f"sqlite:///{metadata_path}"
    test_engine = create_engine(database_url, connect_args={"check_same_thread": False})

    monkeypatch.setattr(db_module, "DB_PATH", metadata_path)
    monkeypatch.setattr(db_module, "DATABASE_URL", database_url)
    monkeypatch.setattr(db_module, "engine", test_engine)

    alembic_cfg = Config(str(db_module.Path(db_module.__file__).resolve().parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        str(db_module.Path(db_module.__file__).resolve().parent / "migrations"),
    )
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_cfg, "d1e2f3a4b5c6")

    with test_engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))

    db_module.init_db()

    with test_engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            )
        }
        agent_session_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(agent_sessions)"))
        }

    assert version == ALEMBIC_HEAD
    assert "agent_messages" in tables
    assert "agent_session_memories" in tables
    assert "reusable_sqls" in tables
    assert "chat_conversations" not in tables
    assert "context_tables_json" in agent_session_columns
