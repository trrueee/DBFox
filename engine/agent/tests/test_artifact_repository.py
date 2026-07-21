from engine.agent.artifact import ArtifactRelationType, ArtifactType
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentArtifactRecord, AgentEventRecord, AgentSession


def test_sql_safety_result_chain_uses_real_ids_and_exact_relations(db_session, test_datasource):
    db_session.add(AgentSession(id="session_artifacts", datasource_id=str(test_datasource.id), title="Artifacts"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_artifacts", datasource_id=str(test_datasource.id),
        datasource_generation=1, content="统计订单", idempotency_key="artifacts",
        llm_credential_id="credential", api_base=None, model_name="model", request_payload={},
    )
    lease = sessions.claim(session_id="session_artifacts", owner="worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease, run_id=admission.run_id, agent_definition_version="1",
        prompt_version="1", prompt_hash="prompt", context_snapshot={}, context_hash="context",
        tool_materialization={}, tool_materialization_hash="tools", provider="test", model_name="test",
    )
    repository = ArtifactRepository(db_session)
    validated = repository.project_tool_result(
        lease=lease, run_id=admission.run_id, turn_id=str(turn.id),
        invocation_id="invocation_validate", tool_name="sql.validate",
        tool_input={"sql": "select count(*) as total from orders"},
        output={
            "can_execute": True, "requires_confirmation": False,
            "risk_level": "safe", "blocked_reasons": [], "messages": [],
            "safe_sql": "select count(*) as total from orders LIMIT 1000",
            "original_sql": "select count(*) as total from orders",
        },
    )
    secret = "reference-only-sensitive-cell"
    result = repository.project_tool_result(
        lease=lease, run_id=admission.run_id, turn_id=str(turn.id),
        invocation_id="invocation_execute", tool_name="sql.execute_readonly", tool_input={},
        output={"columns": ["total"], "rows": [{"total": secret}], "rowCount": 1},
    )
    preview = repository.project_tool_result(
        lease=lease, run_id=admission.run_id, turn_id=str(turn.id),
        invocation_id="invocation_preview", tool_name="db.preview", tool_input={"table": "orders"},
        output={
            "columns": ["id"], "rows": [{"id": secret}], "returned_rows": 1,
            "safe_sql": "SELECT id FROM orders LIMIT 10",
        },
    )
    chart = repository.project_tool_result(
        lease=lease, run_id=admission.run_id, turn_id=str(turn.id),
        invocation_id="invocation_chart", tool_name="chart.suggest", tool_input={},
        output={
            "chartable": True, "type": "bar", "x": "id", "y": "total",
            "aggregation": "sum", "title": "订单合计", "reason": "分类比较",
            "series": [{"label": secret, "value": 1}], "sample_size": 1,
        },
    )
    db_session.commit()

    query = next(item for item in validated if item.type is ArtifactType.SQL)
    safety = next(item for item in validated if item.type is ArtifactType.SAFETY)
    refreshed_query = next(item for item in repository.list_for_run(admission.run_id) if item.id == query.id)
    assert safety.id != query.id
    assert any(
        relation.relation is ArtifactRelationType.VALIDATED_BY and relation.artifact_id == safety.id
        for relation in refreshed_query.relations
    )
    assert any(
        relation.relation is ArtifactRelationType.EXECUTED_AS and relation.artifact_id == result[0].id
        for relation in refreshed_query.relations
    )
    assert result[0].relations[0].artifact_id == query.id
    assert set(result[0].payload) == {
        "sourceSqlArtifactId", "queryFingerprint", "datasourceGeneration", "columns",
        "rowCount", "returnedRows", "latencyMs", "executedAt", "truncated",
    }
    preview_source_id = preview[0].payload["sourceSqlArtifactId"]
    preview_source = next(item for item in repository.list_for_run(admission.run_id) if item.id == preview_source_id)
    assert preview_source.type is ArtifactType.SQL
    assert preview_source.payload["safeSql"] == "SELECT id FROM orders LIMIT 10"
    assert preview[0].relations[0].artifact_id == preview_source.id
    assert set(chart[0].payload) == {
        "sourceResultArtifactId", "chartType", "x", "y", "aggregation", "title",
    }
    assert chart[0].payload["y"] == ["total"]
    durable_artifacts = "".join(
        str(row.payload_json)
        for row in db_session.query(AgentArtifactRecord).filter_by(run_id=admission.run_id).all()
    )
    durable_events = "".join(
        str(row.payload_json)
        for row in db_session.query(AgentEventRecord).filter_by(run_id=admission.run_id).all()
    )
    assert secret not in durable_artifacts
    assert secret not in durable_events
    assert "previewRows" not in durable_artifacts
