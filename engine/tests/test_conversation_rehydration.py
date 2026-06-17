from __future__ import annotations

import json
from datetime import datetime, UTC
import pytest
from fastapi.testclient import TestClient

from engine.main import app, LOCAL_SECURE_TOKEN
from engine.db import get_db
from engine.models import (
    AgentSession,
    AgentRun,
    AgentArtifactRecord,
    ChatConversation,
)
from engine.agent_core.persistence import (
    start_run,
    complete_run,
    fail_run,
    cancel_run,
    sync_chat_conversation_from_session,
)
from engine.agent_core.types import AgentRunRequest, AgentRunResponse, AgentAnswer, AgentWorkspaceContext


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _hdrs():
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def test_start_run_creates_conversation_and_syncs(db_session):
    session_id = "session-test-start"
    run_id = "run-test-start"

    # Create session first
    session = AgentSession(
        id=session_id,
        datasource_id="ds-1",
        title="My Custom Title",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(session)
    db_session.commit()

    workspace_ctx = AgentWorkspaceContext(
        datasource_id="ds-1",
        selected_table_names=["orders", "users"]
    )
    req = AgentRunRequest(
        datasource_id="ds-1",
        question="What is the total revenue?",
        workspace_context=workspace_ctx
    )

    start_run(db_session, req, run_id, session_id)
    db_session.commit()

    # Check that ChatConversation was created
    conv = db_session.query(ChatConversation).filter(ChatConversation.id == session_id).first()
    assert conv is not None
    assert conv.title == "My Custom Title"
    
    tables = json.loads(conv.context_tables_json)
    assert tables == ["orders", "users"]

    messages = json.loads(conv.messages_json)
    assert len(messages) == 2  # user prompt + assistant thinking
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "What is the total revenue?"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "思考中…"


def test_complete_run_syncs_answer_and_visible_artifacts(db_session):
    session_id = "session-test-complete"
    run_id = "run-test-complete"

    # Pre-seed session & run
    session = AgentSession(
        id=session_id,
        datasource_id="ds-1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(session)
    
    run = AgentRun(
        id=run_id,
        session_id=session_id,
        datasource_id="ds-1",
        question="List products",
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()

    # Add visible and hidden artifacts
    # Hidden artifact
    art1 = AgentArtifactRecord(
        id="art-plan",
        run_id=run_id,
        session_id=session_id,
        semantic_id="plan-1",
        type="agent_plan",
        title="Agent Execution Plan",
        produced_by_step="planning",
        payload_json='{"steps": []}',
        presentation_json='{"mode": "hidden"}',
        sequence=1,
        created_at=datetime.now(UTC),
    )
    # Visible SQL
    art2 = AgentArtifactRecord(
        id="art-sql",
        run_id=run_id,
        session_id=session_id,
        semantic_id="sql-exec",
        type="sql",
        title="SQL Execution",
        produced_by_step="execution",
        payload_json='{"sql": "SELECT * FROM products;"}',
        presentation_json='{"mode": "visible"}',
        sequence=2,
        created_at=datetime.now(UTC),
    )
    # Visible Table
    art3 = AgentArtifactRecord(
        id="art-table",
        run_id=run_id,
        session_id=session_id,
        semantic_id="table-results",
        type="table",
        title="Query Results",
        produced_by_step="execution",
        payload_json='{"columns": ["id", "name"], "rows": [{"id": 1, "name": "Apple"}, {"id": 2, "name": "Banana"}], "rowCount": 2}',
        presentation_json='{"mode": "visible"}',
        sequence=3,
        created_at=datetime.now(UTC),
    )
    db_session.add_all([art1, art2, art3])
    db_session.commit()

    # Call complete_run
    ans = AgentAnswer(
        answer="Here are the products.",
        key_findings=["Found 2 products", "Apples and Bananas"],
        caveats=["Database may be cached"]
    )
    resp = AgentRunResponse(
        run_id=run_id,
        session_id=session_id,
        question="List products",
        success=True,
        answer=ans,
        suggestions=[{"label": "Show sales chart", "question": "Show sales chart", "reason": "suggested chart", "action_type": "chart"}]
    )

    complete_run(db_session, resp)
    db_session.commit()

    conv = db_session.query(ChatConversation).filter(ChatConversation.id == session_id).first()
    assert conv is not None
    
    messages = json.loads(conv.messages_json)
    # Expected: User message, Assistant Answer, Suggestions message
    assert len(messages) == 3
    
    # Check user message
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "List products"

    # Check assistant message
    assert messages[1]["role"] == "assistant"
    assert "Here are the products." in messages[1]["content"]
    assert "• Found 2 products" in messages[1]["content"]
    assert "注意：Database may be cached" in messages[1]["content"]

    # Check suggestions message
    assert messages[2]["role"] == "assistant"
    assert "你可以继续问：" in messages[2]["content"]
    assert "Show sales chart" in messages[2]["content"]

    # Check view-level artifacts
    artifacts = json.loads(conv.artifacts_json)
    # Expected: 2 visible artifacts (table and sql) sorted (table first, then sql)
    assert len(artifacts) == 2
    assert artifacts[0]["type"] == "table"
    assert artifacts[0]["columns"] == ["id", "name"]
    assert artifacts[0]["rows"] == [["1", "Apple"], ["2", "Banana"]]
    
    assert artifacts[1]["type"] == "sql"
    assert artifacts[1]["sql"] == "SELECT * FROM products;"


def test_fail_run_syncs_error(db_session):
    session_id = "session-test-fail"
    run_id = "run-test-fail"

    session = AgentSession(
        id=session_id,
        datasource_id="ds-1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(session)
    
    run = AgentRun(
        id=run_id,
        session_id=session_id,
        datasource_id="ds-1",
        question="Crash query",
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()

    fail_run(db_session, run_id, session_id, error="Table not found: orders")
    db_session.commit()

    conv = db_session.query(ChatConversation).filter(ChatConversation.id == session_id).first()
    assert conv is not None
    
    messages = json.loads(conv.messages_json)
    assert len(messages) == 2
    assert messages[1]["role"] == "assistant"
    assert "执行未完成：Table not found: orders" in messages[1]["content"]


def test_conversations_self_healing(db_session):
    """Self-healing is now a startup function, not part of the GET endpoint."""
    from engine.api.conversations import heal_missing_conversations

    # Pre-seed session and runs, but DO NOT create ChatConversation
    session_id = "session-legacy"
    run_id = "run-legacy"

    session = AgentSession(
        id=session_id,
        datasource_id="ds-1",
        title="Legacy Conversation",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(session)

    run = AgentRun(
        id=run_id,
        session_id=session_id,
        datasource_id="ds-1",
        question="What database table is this?",
        status="success",
        response_json='{"explanation": "This is a mysql table."}',
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()

    # Run self-healing directly
    heal_missing_conversations(db_session)

    # Verify that the self-healing actually wrote to the database
    conv = db_session.query(ChatConversation).filter(ChatConversation.id == session_id).first()
    assert conv is not None
    messages = json.loads(conv.messages_json)
    assert len(messages) == 2
    assert messages[0]["content"] == "What database table is this?"
    assert "This is a mysql table." in messages[1]["content"]


def test_conversations_list_api(client, db_session):
    """GET /conversations returns existing ChatConversation rows."""
    session_id = "session-list"

    conv = ChatConversation(
        id=session_id,
        title="Test Conversation",
        created_at=int(datetime.now(UTC).timestamp() * 1000),
        updated_at=int(datetime.now(UTC).timestamp() * 1000),
        context_tables_json="[]",
        messages_json="[]",
        artifacts_json="[]",
    )
    db_session.add(conv)
    db_session.commit()

    resp = client.get("/api/v1/conversations", headers=_hdrs())
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(c["id"] == session_id for c in data)
