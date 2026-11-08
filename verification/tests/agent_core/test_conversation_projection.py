from engine.agent.projection import conversation_snapshot
from engine.agent.repositories.session import SessionRepository
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import AgentRun, AgentSession
from engine.schemas.api_responses import ConversationSummaryResponse
from sqlalchemy import event
from datetime import UTC, datetime
from engine.api.conversation_queries import list_conversations


def test_snapshot_is_backend_owned_and_contains_cursor(db_session, test_resource):
    db_session.add(AgentSession(id="session_projection", title="Projection"))
    db_session.commit()
    admission = SessionRepository(db_session).admit(
        session_id="session_projection", resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
        content="分析数据", idempotency_key="projection", llm_credential_id="credential",
        api_base=None, model_name="model", request_payload={}, selected_artifact_ids=[],
    )
    db_session.commit()
    snapshot = conversation_snapshot(db_session, "session_projection")
    assert snapshot["protocol_version"] == 2
    assert snapshot["items"][0]["type"] == "message"
    assert snapshot["items"][0]["payload"]["role"] == "user"
    assert snapshot["items"][0]["payload"]["content"] == "分析数据"
    assert snapshot["runs"][0]["id"] == admission.run_id
    assert snapshot["cursor"] == 2
    assert snapshot["session"]["selected_artifact_id"] is None


def test_conversation_list_preserves_utc_after_sqlite_reload(db_session):
    instant = datetime(2026, 11, 6, 19, 0, tzinfo=UTC)
    db_session.add(AgentSession(id="session-timezone", title="Timezone", updated_at=instant))
    db_session.commit()
    db_session.expire_all()
    row = next(row for row in list_conversations(limit=50, offset=0, db=db_session)
               if row["id"] == "session-timezone")
    parsed = datetime.fromisoformat(row["updated_at"])
    assert parsed.tzinfo is not None
    assert parsed == instant


def test_list_projects_durable_status_without_loading_each_conversation(db_session):
    db_session.add_all([
        AgentSession(id="idle", title="No runs"),
        AgentSession(id="waiting", title="Needs approval", event_sequence=24),
        AgentSession(id="finished", title="Finished", event_sequence=42),
        AgentSession(id="deleted", title="Deleted", deleted_at=datetime.now(UTC)),
    ])
    db_session.flush()
    db_session.add_all([
        AgentRun(id="waiting-old", session_id="waiting", session_sequence=1, question="a", status="completed"),
        AgentRun(id="waiting-active", session_id="waiting", session_sequence=2, question="b", status="waiting_approval"),
        AgentRun(id="waiting-queue", session_id="waiting", session_sequence=3, question="c", status="queued"),
        AgentRun(id="finished-old", session_id="finished", session_sequence=1, question="a", status="failed"),
        AgentRun(id="finished-latest", session_id="finished", session_sequence=2, question="b", status="completed"),
    ])
    db_session.commit()
    db_session.expire_all()
    statements = []
    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", capture)
    try:
        rows = {row["id"]: row for row in list_conversations(limit=50, offset=0, db=db_session)}
    finally:
        event.remove(bind, "before_cursor_execute", capture)
    assert len(statements) == 1
    assert "deleted" not in rows
    assert rows["idle"]["run_status"] is None
    assert rows["waiting"]["run_status"] == "waiting_approval"
    assert rows["waiting"]["cursor"] == 24
    assert rows["finished"]["run_status"] == "completed"
    assert ConversationSummaryResponse.model_validate(rows["finished"]).cursor == 42
