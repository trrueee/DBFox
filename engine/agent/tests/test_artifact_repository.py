from types import SimpleNamespace

import pytest

from engine.agent.artifact import (
    ArtifactDraft,
    ArtifactRelation,
    ArtifactRelationDraft,
    ArtifactRelationType,
    ArtifactType,
    ArtifactVisibility,
)
from engine.agent.repositories.artifact import (
    ArtifactDraftContractError,
    ArtifactRepository,
)
from engine.agent.repositories.session import SessionRepository
from engine.agent.resource_refs import dump_resource_refs
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import AgentArtifactRecord, AgentRun, AgentSession, AgentSessionInput
from engine.tools.builtin.artifacts import (
    preview_drafts,
    query_result_draft,
    sql_validation_drafts,
)
from dlcs.dbfox_data.backend.tool_contracts import (
    ChartCreateInput,
    DataPreviewOutput,
    QueryResultOutput,
    SqlValidateOutput,
)
from engine.tools.builtin.results import ChartCreateTool
from engine.tools.runtime import ToolRunContext


def _active_run(db_session, test_datasource, session_id: str):
    db_session.add(
        AgentSession(
            id=session_id,
            title="Artifacts",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version="1:1"),),
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


def test_get_for_run_never_exposes_cross_run_or_cross_session_artifacts(
    db_session,
    test_datasource,
):
    admission, lease, turn = _active_run(
        db_session,
        test_datasource,
        "session_artifact_read_scope",
    )
    repository = ArtifactRepository(db_session)
    artifact = repository.create(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        artifact_type=ArtifactType.RESULT_VIEW,
        title="Scoped result",
        payload={
            "sourceSqlArtifactId": "artifact_sql",
            "queryFingerprint": "fingerprint",
            "datasourceGeneration": 1,
            "columns": ["id"],
            "rowCount": 0,
            "returnedRows": 0,
            "latencyMs": 1,
            "executedAt": "2026-08-23T00:00:00Z",
            "truncated": False,
        },
    )

    assert repository.get_for_run(
        session_id=artifact.session_id,
        run_id=artifact.run_id,
        artifact_id=artifact.id,
    ) == artifact
    assert repository.get_for_run(
        session_id=artifact.session_id,
        run_id="another-run",
        artifact_id=artifact.id,
    ) is None
    assert repository.get_for_run(
        session_id="another-session",
        run_id=artifact.run_id,
        artifact_id=artifact.id,
    ) is None


def test_relation_lookup_is_exactly_scoped_to_the_current_run(
    db_session,
    test_datasource,
):
    admission, lease, turn = _active_run(
        db_session,
        test_datasource,
        "session_artifact_relation_scope",
    )
    repository = ArtifactRepository(db_session)
    database_ref = ResourceScopeRef(
        kind="dbfox.data.database",
        id=str(test_datasource.id),
        version="1:1",
    )
    source = repository.create(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        artifact_type=ArtifactType.SQL,
        title="Source SQL",
        resource_refs=(database_ref,),
        payload={
            "sql": "SELECT id FROM users",
            "safeSql": "SELECT id FROM users",
            "dialect": "sqlite",
            "queryFingerprint": "fingerprint",
            "parameters": {},
        },
    )
    result = repository.create(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        artifact_type=ArtifactType.RESULT_VIEW,
        title="Derived result",
        resource_refs=(database_ref,),
        relations=[
            ArtifactRelation(
                relation=ArtifactRelationType.DERIVED_FROM,
                artifact_id=source.id,
            )
        ],
        payload={
            "sourceSqlArtifactId": source.id,
            "queryFingerprint": "fingerprint",
            "datasourceGeneration": 1,
            "columns": ["id"],
            "rowCount": 0,
            "returnedRows": 0,
            "latencyMs": 1,
            "executedAt": "2026-08-23T00:00:00Z",
            "truncated": False,
        },
    )

    assert repository.artifacts_relating_to_for_run(
        session_id=source.session_id,
        run_id=source.run_id,
        artifact_id=source.id,
        relation=ArtifactRelationType.DERIVED_FROM,
    ) == (result,)
    assert repository.artifacts_relating_to_for_run(
        session_id=source.session_id,
        run_id="another-run",
        artifact_id=source.id,
        relation=ArtifactRelationType.DERIVED_FROM,
    ) == ()
def test_previous_result_availability_is_fenced_by_session_generation_and_order(
    db_session,
    test_datasource,
):
    admission, lease, turn = _active_run(
        db_session,
        test_datasource,
        "session_result_fence",
    )
    repository = ArtifactRepository(db_session)
    database_ref = ResourceScopeRef(
        kind="dbfox.data.database",
        id=str(test_datasource.id),
        version="1:1",
    )
    result = repository.create(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        artifact_type=ArtifactType.RESULT_VIEW,
        title="订单结果",
        resource_refs=(database_ref,),
        payload={
            "sourceSqlArtifactId": "artifact_sql",
            "queryFingerprint": "fingerprint",
            "datasourceGeneration": 1,
            "columns": ["id"],
            "rowCount": 1,
            "returnedRows": 1,
            "latencyMs": 10,
            "executedAt": "2026-08-14T00:00:00Z",
            "truncated": False,
            "evidenceKind": "query_result",
        },
    )
    owner_run = db_session.get(AgentRun, admission.run_id)
    assert owner_run is not None
    owner_run.status = "completed"
    current_input = AgentSessionInput(
        id="input_result_consumer",
        session_id="session_result_fence",
        run_id="run_result_consumer",
        sequence=2,
        idempotency_key="input-result-consumer",
        content="继续查看结果",
        resource_refs_json=dump_resource_refs((database_ref,)),
    )
    current_run = AgentRun(
        id="run_result_consumer",
        session_id="session_result_fence",
        input_id=current_input.id,
        session_sequence=2,
        question="继续查看结果",
        status="running",
        request_json="{}",
    )
    db_session.add(current_input)
    db_session.flush()
    db_session.add(current_run)
    db_session.commit()

    def resolve(**overrides):
        return repository.available_result(
            current_run_id=str(overrides.get("current_run_id", current_run.id)),
            artifact_id=str(overrides.get("artifact_id", result.id)),
            session_id=str(overrides.get("session_id", current_run.session_id)),
            resource_ref=ResourceScopeRef(
                kind="dbfox.data.database",
                id=str(overrides.get("datasource_id", test_datasource.id)),
                version=overrides.get("datasource_generation", "1:1"),
            ),
        )

    assert resolve() is not None
    assert resolve(session_id="another_session") is None
    assert resolve(datasource_generation="1:2") is None

    owner_run.status = "running"
    db_session.commit()
    assert resolve() is None

    owner_run.status = "completed"
    owner_run.session_sequence = 3
    db_session.commit()
    assert resolve() is None


@pytest.mark.skip(reason="Data artifact drafting is owned by the dbfox.data System DLC tests")
def test_sql_safety_result_chain_uses_real_ids_and_exact_relations(
    db_session,
    test_datasource,
    monkeypatch,
):
    admission, lease, turn = _active_run(
        db_session,
        test_datasource,
        "session_artifacts",
    )
    repository = ArtifactRepository(db_session)
    database_ref = ResourceScopeRef(
        kind="dbfox.data.database",
        id=str(test_datasource.id),
        version="1:1",
    )
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
                database_ref,
                validation_output,
            )
        ),
    )
    sql_artifact = next(item for item in validated if item.type == ArtifactType.SQL.value)
    safety_artifact = next(
        item for item in validated if item.type == ArtifactType.SAFETY.value
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
                database_ref,
                sql_artifact.id,
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
                database_ref,
                preview_output,
            )
        ),
    )
    sample = next(item for item in preview if item.type == ArtifactType.RESULT_VIEW.value)

    monkeypatch.setattr(
        "engine.tools.builtin.results.ResultViewService.load_verified_source",
        lambda _service, _source: SimpleNamespace(
            fingerprint="query-fingerprint",
        ),
    )
    monkeypatch.setattr(
        "engine.tools.builtin.results.ResultViewService.page",
        lambda _service, _query: SimpleNamespace(
            columns=["bucket", "total"],
            rows=[{"bucket": "paid", "total": 42}],
            has_next_page=True,
        ),
    )
    chart_tool = ChartCreateTool()
    chart_outcome = chart_tool.run(
        ChartCreateInput(
            result_artifact_id=result.id,
            intent="Compare paid orders by status",
            chart_type="bar",
            x="bucket",
            y="total",
            title="订单合计",
        ),
        ToolRunContext.for_invocation(
                request=SimpleNamespace(
                    datasource_id=str(test_datasource.id),
                    datasource_generation=1,
                    session_id=lease.session_id,
                    run_id=admission.run_id,
                ),
            idempotency_key="chart-create-test",
            resources={("dbfox.data.database", str(test_datasource.id)): db_session},
            scope_refs=(database_ref,),
            metadata_session=db_session,
        ),
    )
    chart = repository.persist_drafts(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        invocation_id="invocation_chart",
        tool_name="chart_create",
        drafts=list(chart_outcome.artifacts),
    )[0]
    chart_observation = chart_tool.project_observation(
        status="success",
        output=chart_outcome.output.model_dump(mode="json"),
        artifacts=[chart],
    )
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
    assert chart.payload == {
        "sourceResultArtifactId": result.id,
        "chartType": "bar",
        "x": "bucket",
        "y": ["total"],
        "aggregation": "sum",
        "title": "订单合计",
    }
    assert chart_outcome.output.intent == "Compare paid orders by status"
    assert chart_outcome.output.query_fingerprint == "query-fingerprint"
    assert chart_observation.facts["sample_size"] == 1
    assert chart_observation.facts["sample_truncated"] is True
    assert chart_observation.facts["chart_artifact_id"] == chart.id
    durable = "".join(
        str(row.payload_json)
        for row in db_session.query(AgentArtifactRecord)
        .filter_by(run_id=admission.run_id)
        .all()
    )
    assert secret not in durable
    assert "previewRows" not in durable


@pytest.mark.parametrize(
    "drafts",
    [
        [
            ArtifactDraft(
                key="valid_sql",
                type=ArtifactType.SQL,
                title="Valid SQL",
                payload={
                    "sql": "SELECT 1",
                    "safeSql": "SELECT 1",
                    "dialect": "sqlite",
                    "queryFingerprint": "fingerprint",
                },
            ),
            ArtifactDraft(
                key="invalid_chart",
                type=ArtifactType.CHART,
                title="Invalid chart",
                payload={
                    "sourceResultArtifactId": "artifact_result",
                    "chartType": "bar",
                    "x": "day",
                    "y": ["total"],
                    "aggregation": "none",
                    "title": "Daily total",
                    "unexpected": "not allowed",
                },
            ),
        ],
        [
            ArtifactDraft(
                key="invalid_payload_ref",
                type=ArtifactType.RESULT_VIEW,
                title="Invalid result reference",
                payload={
                    "sourceSqlArtifactId": "",
                    "queryFingerprint": "fingerprint",
                    "datasourceGeneration": 1,
                    "columns": ["total"],
                    "rowCount": 1,
                    "returnedRows": 1,
                    "latencyMs": 1,
                    "executedAt": "2026-08-14T00:00:00Z",
                    "truncated": False,
                    "evidenceKind": "query_result",
                },
                payload_draft_refs={"sourceSqlArtifactId": "missing_sql"},
            )
        ],
        [
            ArtifactDraft(
                key="invalid_relation",
                type=ArtifactType.SQL,
                title="Invalid relation",
                payload={
                    "sql": "SELECT 1",
                    "safeSql": "SELECT 1",
                    "dialect": "sqlite",
                    "queryFingerprint": "fingerprint",
                },
                relations=(
                    ArtifactRelationDraft(
                        relation=ArtifactRelationType.DERIVED_FROM,
                        draft_key="missing_source",
                    ),
                ),
            )
        ],
    ],
    ids=["payload", "payload-draft-reference", "relation-draft-reference"],
)
def test_artifact_batch_contract_failure_precedes_every_write(
    db_session,
    test_datasource,
    drafts,
):
    admission, lease, turn = _active_run(
        db_session,
        test_datasource,
        "session_invalid_artifact_batch",
    )
    before = (
        db_session.query(AgentArtifactRecord)
        .filter_by(run_id=admission.run_id)
        .count()
    )

    with pytest.raises(ArtifactDraftContractError):
        ArtifactRepository(db_session).persist_drafts(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            invocation_id="invocation_invalid_batch",
            tool_name="invalid_artifact_tool",
            drafts=drafts,
        )

    assert (
        db_session.query(AgentArtifactRecord)
        .filter_by(run_id=admission.run_id)
        .count()
        == before
    )


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


def test_artifact_draft_cannot_expand_run_resource_authority(
    db_session,
    test_datasource,
) -> None:
    admission, lease, turn = _active_run(
        db_session,
        test_datasource,
        "session_artifact_resource_fence",
    )
    unauthorized = ResourceScopeRef(
        kind="dbfox.data.database",
        id="database-outside-run",
        version="1:1",
    )

    with pytest.raises(
        ArtifactDraftContractError,
        match="subset of the Run authority",
    ):
        ArtifactRepository(db_session).persist_drafts(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            invocation_id="invocation_unauthorized_artifact",
            tool_name="example_tool",
            drafts=[
                ArtifactDraft(
                    key="outside",
                    type=ArtifactType.MARKDOWN,
                    title="Outside authority",
                    payload={"content": "bounded"},
                    resource_refs=(unauthorized,),
                )
            ],
        )
