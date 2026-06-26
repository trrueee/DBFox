from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from engine.db import Base


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

    assert version == "0a1b2c3d4e5f"
