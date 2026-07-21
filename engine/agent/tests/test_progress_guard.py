import json

from engine.agent.progress_guard import ProgressGuard
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentArtifactRecord, AgentRun, AgentSession


def _admit(db_session, test_datasource, session_id: str):
    db_session.add(AgentSession(id=session_id, datasource_id=str(test_datasource.id), title="Progress"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="分析数据",
        idempotency_key=f"{session_id}:input",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="worker")
    sessions.promote_next_input(lease=lease)
    db_session.commit()
    return admission, lease


def test_progress_fingerprint_ignores_duplicate_record_identity_and_timing(db_session, test_datasource):
    admission, _lease = _admit(db_session, test_datasource, "session_progress_fingerprint")
    common = {
        "run_id": admission.run_id,
        "session_id": "session_progress_fingerprint",
        "type": "result_view",
        "title": "订单统计",
        "semantic_id": "orders:count",
        "presentation_json": "{}",
        "provenance_json": "{}",
        "relations_json": "[]",
        "status": "completed",
    }
    db_session.add(AgentArtifactRecord(
        id="artifact_progress_1",
        payload_json=json.dumps({
            "sourceSqlArtifactId": "artifact_sql_1",
            "queryFingerprint": "query-a",
            "rowCount": 1,
            "executedAt": "2026-01-01T00:00:00Z",
            "latencyMs": 10,
        }),
        **common,
    ))
    db_session.commit()
    first = ProgressGuard(db_session).fingerprint(admission.run_id)

    db_session.add(AgentArtifactRecord(
        id="artifact_progress_2",
        payload_json=json.dumps({
            "sourceSqlArtifactId": "artifact_sql_2",
            "queryFingerprint": "query-a",
            "rowCount": 1,
            "executedAt": "2026-01-02T00:00:00Z",
            "latencyMs": 99,
        }),
        **common,
    ))
    db_session.commit()
    assert ProgressGuard(db_session).fingerprint(admission.run_id) == first

    db_session.add(AgentArtifactRecord(
        id="artifact_progress_3",
        payload_json=json.dumps({"queryFingerprint": "query-b", "rowCount": 2}),
        **{**common, "semantic_id": "orders:count:new"},
    ))
    db_session.commit()
    assert ProgressGuard(db_session).fingerprint(admission.run_id) != first


def test_progress_counter_survives_focus_updates(db_session, test_datasource):
    admission, lease = _admit(db_session, test_datasource, "session_progress_state")
    repository = RunRepository(db_session)
    assert repository.record_progress(
        lease=lease, run_id=admission.run_id, fingerprint="same-state",
    ) == 0
    db_session.commit()
    repository.record_focus(
        lease=lease, run_id=admission.run_id, kind="continue",
        reason="需要更多证据", missing=["trend"],
    )
    db_session.commit()
    assert repository.record_progress(
        lease=lease, run_id=admission.run_id, fingerprint="same-state",
    ) == 1
    db_session.commit()

    state = json.loads(db_session.get(AgentRun, admission.run_id).result_json)
    assert state["progress"]["stalled_turns"] == 1
    assert state["focus"]["missing"] == ["trend"]
