"""Folder-name migration preserves project and conversation identities."""
from alembic import command
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from engine.db import build_alembic_config, build_metadata_engine
from engine.models import AgentSession, Project

pytestmark = pytest.mark.migration


def test_folder_names_upgrade_and_guarded_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'folders.sqlite3'}"
    config = build_alembic_config(url)
    command.upgrade(config, "f7a8b9c0d0ed")
    engine = build_metadata_engine(url)
    try:
        with Session(engine) as session:
            session.add(Project(id="folder-one", name="workspace", status="active"))
            session.flush()
            session.add(AgentSession(id="old-conversation", project_id="folder-one", title="保留的对话"))
            session.commit()
        command.upgrade(config, "f8a9b0c1d2ee")
        with Session(engine) as session:
            session.add(Project(id="folder-two", name="workspace", status="active"))
            session.commit()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT project_id FROM agent_sessions WHERE id='old-conversation'")).scalar_one() == "folder-one"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        assert "uq_projects_name" not in {item["name"] for item in inspect(engine).get_unique_constraints("projects")}
        with pytest.raises(RuntimeError, match="Project names must be distinct"):
            command.downgrade(config, "f7a8b9c0d0ed")
        with engine.begin() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM projects WHERE name='workspace'")).scalar_one() == 2
            connection.execute(text("UPDATE projects SET name='other' WHERE id='folder-two'"))
        command.downgrade(config, "f7a8b9c0d0ed")
        assert "uq_projects_name" in {item["name"] for item in inspect(engine).get_unique_constraints("projects")}
        command.upgrade(config, "f8a9b0c1d2ee")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM agent_sessions WHERE id='old-conversation'")).scalar_one() == 1
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        engine.dispose()
