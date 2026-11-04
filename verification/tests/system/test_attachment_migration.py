"""Attachment schema upgrade preserves old conversations and supports rollback."""
from alembic import command
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from engine.db import build_alembic_config, build_metadata_engine
from engine.models import AgentSession

pytestmark = pytest.mark.migration


def test_attachment_upgrade_downgrade_preserves_existing_conversation(tmp_path):
    url = f"sqlite:///{tmp_path / 'migration.sqlite'}"
    config = build_alembic_config(url)
    command.upgrade(config, "f6a7b8c9d0ec")
    engine = build_metadata_engine(url)
    try:
        with Session(engine) as db:
            db.add(AgentSession(id="old-conversation", title="已有会话"))
            db.commit()
        command.upgrade(config, "f7a8b9c0d0ed")
        schema = inspect(engine)
        assert {"conversation_attachments", "session_resource_retirements"} <= set(schema.get_table_names())
        assert "request_fingerprint" in {c["name"] for c in schema.get_columns("agent_session_inputs")}
        with engine.connect() as db:
            assert db.execute(text("SELECT title FROM agent_sessions WHERE id='old-conversation'")).scalar_one() == "已有会话"
            assert db.execute(text("PRAGMA foreign_key_check")).all() == []
        command.downgrade(config, "f6a7b8c9d0ec")
        assert "conversation_attachments" not in inspect(engine).get_table_names()
        assert "request_fingerprint" not in {c["name"] for c in inspect(engine).get_columns("agent_session_inputs")}
        command.upgrade(config, "f7a8b9c0d0ed")
        with engine.connect() as db:
            assert db.execute(text("SELECT COUNT(*) FROM agent_sessions WHERE id='old-conversation'")).scalar_one() == 1
    finally:
        engine.dispose()
