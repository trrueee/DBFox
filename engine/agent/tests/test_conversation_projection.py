from engine.agent.projection import conversation_snapshot
from engine.agent.repositories.session import SessionRepository
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import AgentSession


def test_snapshot_is_backend_owned_and_contains_cursor(db_session, test_datasource):
    db_session.add(AgentSession(id="session_projection", title="Projection"))
    db_session.commit()
    admission = SessionRepository(db_session).admit(
        session_id="session_projection", resource_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version=1),),
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
