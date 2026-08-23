import json

from engine.agent.progress_guard import ProgressGuard, observation_evidence_signatures
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import AgentArtifactRecord, AgentRun, AgentSession
from engine.tools.builtin.query import SqlValidateTool


def _admit(db_session, test_datasource, session_id: str):
    db_session.add(AgentSession(id=session_id, title="Progress"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version="1:1"),),
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
        **{**common, "semantic_id": "result:invocation-2"},
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


def test_progress_fingerprint_ignores_procedural_sql_and_safety_artifacts(db_session, test_datasource):
    admission, _lease = _admit(db_session, test_datasource, "session_progress_procedure")
    first = ProgressGuard(db_session).fingerprint(admission.run_id)
    common = {
        "run_id": admission.run_id,
        "session_id": "session_progress_procedure",
        "title": "SQL 过程状态",
        "provenance_json": "{}",
        "relations_json": "[]",
        "status": "completed",
    }
    db_session.add_all([
        AgentArtifactRecord(
            id="artifact_progress_sql",
            type="sql",
            semantic_id="sql:one",
            payload_json=json.dumps({"sql": "SELECT 1", "safeSql": "SELECT 1 LIMIT 500"}),
            presentation_json=json.dumps({"visibility": "supporting"}),
            **common,
        ),
        AgentArtifactRecord(
            id="artifact_progress_safety",
            type="safety",
            semantic_id="safety:one",
            payload_json=json.dumps({"canExecute": True}),
            presentation_json=json.dumps({"visibility": "internal"}),
            **common,
        ),
    ])
    db_session.commit()

    assert ProgressGuard(db_session).fingerprint(admission.run_id) == first


def _signatures(tool_name: str, facts: dict):
    return observation_evidence_signatures(
        tool_name=tool_name,
        status="succeeded",
        facts=facts,
        error_code="",
    )


def test_empty_catalog_queries_have_one_stable_evidence_signature() -> None:
    first = _signatures("schema_search", {"returned_count": 0, "candidates": []})
    synonym = _signatures(
        "schema_search",
        {"returned_count": 0, "candidates": []},
    )

    assert first == synonym


def test_catalog_candidate_score_and_matched_query_do_not_fake_progress() -> None:
    first = _signatures(
        "schema_search",
        {
            "candidates": [
                {
                    "type": "table",
                    "schema_name": "main",
                    "table_name": "orders",
                    "score": 1.0,
                    "matched_queries": ["order"],
                }
            ]
        },
    )
    synonym = _signatures(
        "schema_search",
        {
            "candidates": [
                {
                    "type": "table",
                    "schema_name": "main",
                    "table_name": "orders",
                    "score": 0.72,
                    "matched_queries": ["purchase"],
                }
            ]
        },
    )

    assert first == synonym


def test_new_catalog_identity_is_meaningful_progress() -> None:
    orders = _signatures(
        "schema_list",
        {"tables": [{"schema_name": "main", "table_name": "orders"}]},
    )
    customers = _signatures(
        "schema_list",
        {"tables": [{"schema_name": "main", "table_name": "customers"}]},
    )

    assert orders != customers


def test_non_catalog_result_remains_an_atomic_observation() -> None:
    first = _signatures("sql_execute_readonly", {"row_count": 1, "total": 42})
    changed = _signatures("sql_execute_readonly", {"row_count": 1, "total": 43})

    assert first != changed


def test_non_catalog_score_remains_meaningful() -> None:
    first = _signatures("result_profile", {"quality_score": 0.8, "score": 10})
    changed = _signatures("result_profile", {"quality_score": 0.8, "score": 11})

    assert first != changed


def test_sql_validation_progress_is_bounded_to_readiness_transitions() -> None:
    assert SqlValidateTool.semantics.contributes_progress is True

    first_rejection = _signatures(
        "sql_validate",
        {
            "can_execute": False,
            "blocked_reasons": ["unsupported_cte"],
            "messages": ["Rewrite the query."],
        },
    )
    rewritten_rejection = _signatures(
        "sql_validate",
        {
            "can_execute": False,
            "blocked_reasons": ["unsupported_window"],
            "messages": ["Try another SQL shape."],
        },
    )
    executable = _signatures(
        "sql_validate",
        {
            "can_execute": True,
            "validation_artifact_id": "artifact_sql_ready",
            "messages": [],
        },
    )
    another_executable = _signatures(
        "sql_validate",
        {
            "can_execute": True,
            "validation_artifact_id": "artifact_sql_also_ready",
            "messages": ["EXPLAIN completed."],
        },
    )

    assert first_rejection == rewritten_rejection
    assert executable == another_executable
    assert executable != first_rejection
