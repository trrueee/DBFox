from __future__ import annotations

from datetime import UTC, datetime

from engine.agent_core.persistence import get_conversation_detail
from engine.agent_core.persistence_sink import create_persistence_sink
from engine.agent_core.types import AgentRunRequest, AgentRunResponse
from engine.models import (
    AgentArtifactRecord,
    AgentMessage,
    AgentRun,
    AgentSession,
)


def test_conversation_message_run_artifact_links(db_session):
    now = datetime.now(UTC)
    session = AgentSession(
        id="conv-contract",
        datasource_id="ds-1",
        title="Revenue chat",
        context_tables_json='["orders"]',
        created_at=now,
        updated_at=now,
    )
    user = AgentMessage(
        id="msg-user-1",
        session_id=session.id,
        role="user",
        content="Show revenue",
        status="completed",
        sequence=1,
        created_at=now,
        updated_at=now,
    )
    assistant = AgentMessage(
        id="msg-assistant-1",
        session_id=session.id,
        role="assistant",
        content="",
        status="streaming",
        sequence=2,
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id="run-1",
        session_id=session.id,
        datasource_id="ds-1",
        user_message_id=user.id,
        assistant_message_id=assistant.id,
        question="Show revenue",
        status="running",
        created_at=now,
        updated_at=now,
    )
    artifact = AgentArtifactRecord(
        id="artifact-sql-1",
        run_id=run.id,
        session_id=session.id,
        message_id=assistant.id,
        semantic_id="sql-1",
        type="sql",
        title="SQL 1",
        payload_json='{"sql": "select 1"}',
        presentation_json='{"mode": "visible"}',
        depends_on_json="[]",
        status="completed",
        sequence=1,
        created_at=now,
    )

    db_session.add_all([session, user, assistant, run, artifact])
    db_session.commit()

    saved = db_session.get(AgentSession, session.id)
    assert saved is not None
    assert [message.id for message in saved.messages] == ["msg-user-1", "msg-assistant-1"]
    assert saved.runs[0].user_message_id == "msg-user-1"
    assert saved.runs[0].assistant_message_id == "msg-assistant-1"
    assert saved.runs[0].artifacts[0].message_id == "msg-assistant-1"


def test_persistence_sink_creates_user_and_assistant_messages(db_session):
    sink = create_persistence_sink(db_session)
    req = AgentRunRequest(datasource_id="ds-1", question="Count users", session_id="conv-sink")

    sink.start_run(req, run_id="run-sink", session_id="conv-sink")
    db_session.commit()

    detail = get_conversation_detail(db_session, "conv-sink")
    assert detail is not None
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "Count users"
    assert detail["messages"][1]["status"] == "streaming"
    assert detail["runs"][0]["user_message_id"] == detail["messages"][0]["id"]
    assert detail["runs"][0]["assistant_message_id"] == detail["messages"][1]["id"]


def test_persistence_sink_completes_assistant_message(db_session):
    sink = create_persistence_sink(db_session)
    req = AgentRunRequest(datasource_id="ds-1", question="Count users", session_id="conv-sink-complete")
    sink.start_run(req, run_id="run-sink-complete", session_id="conv-sink-complete")
    response = AgentRunResponse(
        run_id="run-sink-complete",
        session_id="conv-sink-complete",
        success=True,
        status="completed",
        question="Count users",
        explanation="There are 10 users.",
        artifacts=[],
    )

    sink.complete_run(response)
    db_session.commit()

    detail = get_conversation_detail(db_session, "conv-sink-complete")
    assert detail is not None
    assistant = detail["messages"][1]
    assert assistant["role"] == "assistant"
    assert assistant["status"] == "completed"
    assert "There are 10 users." in assistant["content"]
