from __future__ import annotations

from datetime import UTC, datetime

from engine.agent_core.persistence import get_conversation_detail
from engine.models import AgentMessage, AgentRun, AgentSession


def test_conversation_detail_rehydrates_from_structured_tables(db_session):
    now = datetime.now(UTC)
    session = AgentSession(
        id="conv-rehydrate",
        datasource_id="ds-1",
        title="Structured",
        created_at=now,
        updated_at=now,
    )
    user = AgentMessage(
        id="msg-rehydrate-user",
        session_id=session.id,
        role="user",
        content="Hello",
        status="completed",
        sequence=1,
        created_at=now,
        updated_at=now,
    )
    assistant = AgentMessage(
        id="msg-rehydrate-assistant",
        session_id=session.id,
        role="assistant",
        content="Hi",
        status="completed",
        sequence=2,
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id="run-rehydrate",
        session_id=session.id,
        datasource_id="ds-1",
        user_message_id=user.id,
        assistant_message_id=assistant.id,
        question="Hello",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([session, user, assistant, run])
    db_session.commit()

    detail = get_conversation_detail(db_session, session.id)
    assert detail is not None
    assert [message["content"] for message in detail["messages"]] == ["Hello", "Hi"]
    assert detail["runs"][0]["assistant_message_id"] == "msg-rehydrate-assistant"
