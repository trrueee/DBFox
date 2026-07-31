import pytest

from engine.agent.artifact import (
    ArtifactDraft,
    ArtifactRelationDraft,
    ArtifactRelationType,
    ArtifactType,
    ArtifactVisibility,
)
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentArtifactRecord, AgentSession
from engine.tools.builtin.artifacts import (
    preview_drafts,
    query_result_draft,
    sql_validation_drafts,
)
from engine.tools.builtin.contracts import (
    DataPreviewOutput,
    QueryResultOutput,
    SqlValidateOutput,
)


def _active_run(db_session, test_datasource, session_id: str):
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Artifacts",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计订单",
        idempotency_key=f"request-{session_id}",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="worker")
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization={},
        tool_materialization_hash="tools",
        provider="test",
        model_name="test",
    )
    return admission, lease, turn


def test_sql_safety_result_chain_uses_real_ids_and_exact_relations(
    db_session,
    test_datasource,
):
    admission, lease, turn = _active_run(
        db_session,
        test_datasource,
        "session_artifacts",
    )
    repository = ArtifactRepository(db_session)
    decision = {
        "datasource_id": str(test_datasource.id),
        "policy": "agent_readonly",
        "original_sql": "select count(*) as total from orders",
        "safe_sql": "select count(*) as total from orders LIMIT 1000",
        "passed": True,
        "can_execute": True,
        "requires_confirmation": False,
        "risk_level": "safe",
        "guardrail": {},
        "schema_warnings": [],
        "scope_state": {},
        "blocked_reasons": [],
        "messages": [],
    }
    validation_output = SqlValidateOutput(
        can_execute=True,
        requires_confirmation=False,
        safe_sql=decision["safe_sql"],
        original_sql=decision["original_sql"],
        risk_level="safe",
        blocked_reasons=[],
        messages=[],
        execution_safety_decision=decision,
    )
    validated = repository.persist_drafts(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        invocation_id="invocation_validate",
        tool_name="sql_validate",
        drafts=list(
            sql_validation_drafts(
                db_session,
                str(test_datasource.id),
                validation_output,
            )
        ),
    )
    sql_artifact = next(item for item in validated if item.type is ArtifactType.SQL)
    safety_artifact = next(
        item for item in validated if item.type is ArtifactType.SAFETY
    )

    secret = "reference-only-sensitive-cell"
    query_output = QueryResultOutput(
        status="success",
        success=True,
        row_count=1,
        columns=["total"],
        column_types=["text"],
        returned_rows=1,
        truncated=False,
        rows=[{"total": secret}],
        safe_sql=decision["safe_sql"],
        execution_time_ms=1,
        warnings=[],
        audit={"history_id": "history-result"},
        latency_ms=1,
    )
    result = repository.persist_drafts(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        invocation_id="invocation_execute",
        tool_name="sql_execute_readonly",
        drafts=[
            query_result_draft(
                db_session,
                str(test_datasource.id),
                sql_artifact.id,
                1,
                query_output,
            )
        ],
    )[0]

    preview_output = DataPreviewOutput(
        table="orders",
        columns=["id"],
        returned_rows=1,
        limit_applied=10,
        rows=[{"id": secret}],
        safe_sql="SELECT id FROM orders LIMIT 10",
        truncated=False,
        warnings=[],
        column_summaries=[],
        audit={"history_id": "history-preview"},
        latency_ms=1,
    )
    preview = repository.persist_drafts(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        invocation_id="invocation_preview",
        tool_name="data_preview",
        drafts=list(
            preview_drafts(
                db_session,
                str(test_datasource.id),
                1,
                preview_output,
            )
        ),
    )
    sample = next(item for item in preview if item.type is ArtifactType.RESULT_VIEW)

    chart = repository.persist_drafts(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        invocation_id="invocation_chart",
        tool_name="chart_create",
        drafts=[
            ArtifactDraft(
                key="chart",
                type=ArtifactType.CHART,
                title="订单合计",
                payload={
                    "sourceResultArtifactId": result.id,
                    "chartType": "bar",
                    "x": "id",
                    "y": ["total"],
                    "aggregation": "sum",
                    "title": "订单合计",
                },
                relations=(
                    ArtifactRelationDraft(
                        relation=ArtifactRelationType.DERIVED_FROM,
                        artifact_id=result.id,
                    ),
                ),
            )
        ],
    )[0]
    db_session.commit()

    persisted_sql = next(
        item
        for item in repository.list_for_run(admission.run_id)
        if item.id == sql_artifact.id
    )
    assert safety_artifact.visibility is ArtifactVisibility.INTERNAL
    assert sql_artifact.visibility is ArtifactVisibility.SUPPORTING
    assert result.visibility is ArtifactVisibility.PRIMARY
    assert sample.payload["evidenceKind"] == "sample_rows"
    assert result.payload["evidenceKind"] == "query_result"
    assert any(
        relation.relation is ArtifactRelationType.VALIDATED_BY
        and relation.artifact_id == safety_artifact.id
        for relation in persisted_sql.relations
    )
    assert result.relations[0].artifact_id == sql_artifact.id
    assert chart.relations[0].artifact_id == result.id
    durable = "".join(
        str(row.payload_json)
        for row in db_session.query(AgentArtifactRecord)
        .filter_by(run_id=admission.run_id)
        .all()
    )
    assert secret not in durable
    assert "previewRows" not in durable


def test_result_artifact_rejects_embedded_rows_before_persistence(
    db_session,
    test_datasource,
):
    admission, lease, turn = _active_run(
        db_session,
        test_datasource,
        "session_artifact_boundary",
    )
    with pytest.raises(
        ValueError,
        match=r"cannot persist result values at payload\.rows",
    ):
        ArtifactRepository(db_session).create(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            artifact_type=ArtifactType.RESULT_VIEW,
            title="订单结果",
            payload={
                "sourceSqlArtifactId": "artifact_sql",
                "queryFingerprint": "fingerprint",
                "datasourceGeneration": 1,
                "columns": ["id"],
                "rowCount": 1,
                "returnedRows": 1,
                "latencyMs": 10,
                "executedAt": "2026-07-24T00:00:00Z",
                "truncated": False,
                "evidenceKind": "query_result",
                "rows": [{"id": "sensitive"}],
            },
        )
    assert (
        db_session.query(AgentArtifactRecord)
        .filter_by(run_id=admission.run_id)
        .count()
        == 0
    )
