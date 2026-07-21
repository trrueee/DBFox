import json
import asyncio
import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from unittest.mock import MagicMock
from pydantic import ValidationError

import engine.api.agent as agent_module
from fastapi import HTTPException

from engine.api.agent import ResultPageRequest
from engine.datasource import datasource_connection_dict
from engine.projects.service import resolve_project_id, get_or_create_default_project, Project
from engine.models import DEFAULT_PROJECT_ID, AgentArtifactRecord, AgentRun, AgentSession, DataSource, SchemaColumn, SchemaTable
from engine.sql.trust_gate import ExecutionSafetyDecision
from engine.sql.result_view.fingerprint import result_source_fingerprint


def _add_pagination_source(
    db_session,
    *,
    artifact_id: str = "artifact-sql-page",
    artifact_type: str = "sql",
    safe_sql: str = "SELECT id, amount FROM orders",
    columns: list[str] | None = None,
) -> str:
    now = datetime.now(UTC)
    datasource = DataSource(
        id="ds-page",
        name="Page DS",
        db_type="mysql",
        host="localhost",
        port=3306,
        database_name="dbfox",
        username="root",
        connection_generation=1,
    )
    session = AgentSession(
        id="conv-page",
        datasource_id="ds-page",
        title="Page",
        context_tables_json="[]",
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id="run-page",
        session_id="conv-page",
        datasource_id="ds-page",
        datasource_generation=1,
        llm_credential_id="credential-page",
        question="Orders",
        request_json=json.dumps({"question": "Orders"}),
        status="completed",
        version=2,
        cancel_requested=False,
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    artifact = AgentArtifactRecord(
        id=artifact_id,
        run_id="run-page",
        session_id="conv-page",
        semantic_id="sql_candidate",
        type=artifact_type,
        title="Orders SQL",
        payload_json=json.dumps(
            {
                "safeSql": safe_sql,
                "dialect": "mysql",
                "queryFingerprint": result_source_fingerprint(safe_sql, "mysql"),
            }
        ),
        presentation_json=json.dumps({"mode": "both", "priority": 1, "collapsed": False}),
        depends_on_json=json.dumps(["safety_candidate"]),
        refs_json="{}",
        relations_json="[]",
        status="completed",
        sequence=1,
        created_at=now,
    )
    # The fixture uses scalar FK IDs rather than ORM relationships. Flush each
    # parent first so strict SQLite foreign-key enforcement validates the same
    # insertion order required by real persistence code.
    db_session.add(datasource)
    db_session.flush()
    db_session.add(session)
    db_session.flush()
    db_session.add(run)
    db_session.flush()
    db_session.add(artifact)
    db_session.flush()
    result_id = f"result-for-{artifact_id}"
    db_session.add(AgentArtifactRecord(
        id=result_id,
        run_id="run-page",
        session_id="conv-page",
        semantic_id="result_view",
        type="result_view",
        title="Orders result",
        payload_json=json.dumps({
            "sourceSqlArtifactId": artifact_id,
            "queryFingerprint": result_source_fingerprint(safe_sql, "mysql"),
            "datasourceGeneration": 1,
            "columns": columns or ["id", "amount"],
        }),
        presentation_json="{}",
        depends_on_json=json.dumps([artifact_id]),
        refs_json="{}",
        relations_json=json.dumps([{"relation": "derived_from", "artifact_id": artifact_id}]),
        status="completed",
        sequence=2,
        created_at=now,
    ))
    db_session.commit()
    return result_id


def _add_table_result_source(
    db_session,
    *,
    datasource_id: str = "ds-table-page",
    table_id: str = "schema-table-page-orders",
    table_name: str = "orders",
) -> None:
    datasource = DataSource(
        id=datasource_id,
        name="Table Page DS",
        db_type="mysql",
        host="localhost",
        port=3306,
        database_name="dbfox",
        username="root",
    )
    table = SchemaTable(
        id=table_id,
        data_source_id=datasource_id,
        table_schema="dbfox",
        table_name=table_name,
        table_type="BASE TABLE",
    )
    columns = [
        SchemaColumn(id="schema-col-page-id", table_id=table_id, column_name="id", data_type="integer", ordinal_position=1),
        SchemaColumn(id="schema-col-page-amount", table_id=table_id, column_name="amount", data_type="decimal", ordinal_position=2),
        SchemaColumn(id="schema-col-page-status", table_id=table_id, column_name="status", data_type="text", ordinal_position=3),
    ]
    db_session.add_all([datasource, table, *columns])
    db_session.commit()


def _add_console_datasource(db_session, *, datasource_id: str = "ds-console") -> None:
    db_session.add(
        DataSource(
            id=datasource_id,
            name="Console DS",
            db_type="mysql",
            host="localhost",
            port=3306,
            database_name="dbfox",
            username="root",
            connection_generation=11,
        )
    )
    db_session.commit()


def test_reusable_sql_memory_is_not_public_agent_api():
    route_paths = {getattr(route, "path", "") for route in agent_module.router.routes}

    assert "/agent/reusable-sqls" not in route_paths


def test_legacy_agent_run_surface_is_removed() -> None:
    retired_symbols = (
        "api_agent_run",
        "api_agent_run_resume",
        "api_agent_run_stream",
        "api_agent_run_resume_stream",
        "api_cancel_agent_run",
        "api_resolve_agent_approval",
        "api_get_agent_run",
    )
    assert all(not hasattr(agent_module, symbol) for symbol in retired_symbols)


def test_llm_test_uses_product_config_and_factory(monkeypatch):
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["completion"] = kwargs

    def fake_create_client(**kwargs):
        captured["client_kwargs"] = kwargs
        return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    def fake_resolve_product_config(**kwargs):
        captured["resolve_kwargs"] = kwargs
        return SimpleNamespace(
            model_name="qwen-plus",
            api_key="test-secret",
            api_base="https://example.test/v1",
            source="product",
        )

    monkeypatch.setattr(
        agent_module,
        "resolve_product_llm_config_from_credential",
        fake_resolve_product_config,
    )
    monkeypatch.setattr(agent_module, "create_openai_compatible_api_client", fake_create_client)

    response = agent_module.api_llm_test(
        agent_module.LlmTestRequest(
            llm_credential_id="cred_llm_api_key_test",
            api_base="https://example.test/v1",
            model_name="qwen-plus",
        )
    )

    resolve_kwargs = captured["resolve_kwargs"]
    assert response.ok is True
    assert response.model == "qwen-plus"
    assert response.api_base == "https://example.test/v1"
    assert captured["completion"] == {
        "model": "qwen-plus", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1,
    }
    assert captured["client_kwargs"] == {
        "api_key": "test-secret", "api_base": "https://example.test/v1", "timeout": 10.0,
    }
    assert resolve_kwargs == {
        "llm_credential_id": "cred_llm_api_key_test",
        "api_base": "https://example.test/v1",
        "model_name": "qwen-plus",
    }


def test_llm_test_requires_opaque_credential_reference_even_when_env_exists(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "TEST_LLM_SECRET")

    with pytest.raises(ValidationError):
        agent_module.LlmTestRequest(
            api_base="https://example.test/v1",
            model_name="qwen-plus",
        )


def _console_decision(datasource_id: str, sql: str) -> ExecutionSafetyDecision:
    return ExecutionSafetyDecision(
        datasource_id=datasource_id,
        policy="user_readonly",
        original_sql=sql,
        safe_sql=sql,
        passed=True,
        can_execute=True,
        requires_confirmation=False,
        guardrail={
            "result": "pass",
            "originalSql": sql,
            "safeSql": sql,
            "checks": [],
            "message": "ok",
        },
        schema_warnings=[],
        scope_state={"source": "sql_console"},
        messages=[],
    )


def test_console_execute_persists_sql_backed_artifact_chain(monkeypatch, db_session):
    _add_console_datasource(db_session)
    request_model = getattr(agent_module, "ConsoleExecuteRequest", None)
    assert request_model is not None
    execute_api = getattr(agent_module, "api_agent_console_execute", None)
    assert execute_api is not None
    sql = "SELECT id, name FROM users"

    def fake_build_execution_decision(_self, requested_sql, ctx, policy):
        assert policy == "user_readonly"
        assert ctx.datasource_id == "ds-console"
        return _console_decision("ds-console", requested_sql)

    def fake_execute_query(_db, datasource_id, requested_sql, question=None, execution_id=None, **kwargs):
        safety_decision = kwargs["safety_decision"]
        assert datasource_id == "ds-console"
        assert requested_sql == sql
        assert question == "SQL Console"
        assert safety_decision.safe_sql == sql
        return {
            "success": True,
            "columns": ["id", "name"],
            "rows": [{"id": 1, "name": "Ada"}],
            "rowCount": 1,
            "latencyMs": 5,
            "warnings": ["preview warning"],
            "notices": ["preview notice"],
            "truncated": False,
            "historyId": "history-console-1",
            "executionId": execution_id,
            "safetyDecision": safety_decision.model_dump(mode="json"),
        }

    monkeypatch.setattr(agent_module.SqlSafetyService, "build_execution_decision", fake_build_execution_decision)
    monkeypatch.setattr("engine.sql.executor.execute_query", fake_execute_query)

    response = execute_api(
        request_model(
            datasourceId="ds-console",
            sql=sql,
            question="SQL Console",
            sessionId="console-session",
            executionId="console-exec-1",
        ),
        db_session,
    )

    assert response.sessionId == "console-session"
    assert response.sqlArtifactId
    assert response.safetyArtifactId
    assert response.resultArtifactId
    assert response.warnings == ["preview warning"]
    assert response.notices == ["preview notice"]

    records = (
            db_session.query(AgentArtifactRecord)
            .filter(AgentArtifactRecord.run_id == response.runId)
            .order_by(AgentArtifactRecord.sequence)
        .all()
    )
    assert [record.type for record in records] == ["safety", "sql", "result_view"]
    result_record = next(record for record in records if record.type == "result_view")
    sql_record = next(record for record in records if record.type == "sql")
    safety_record = next(record for record in records if record.type == "safety")
    result_payload = json.loads(result_record.payload_json)

    assert result_payload["sourceSqlArtifactId"] == sql_record.id
    assert safety_record.id
    assert "rows" not in result_payload
    assert "previewRows" not in result_payload
    assert result_payload["queryFingerprint"]
    assert set(result_payload) == {
        "sourceSqlArtifactId", "queryFingerprint", "datasourceGeneration", "columns",
        "rowCount", "returnedRows", "latencyMs", "executedAt", "truncated",
    }

    run = db_session.get(AgentRun, response.runId)
    assert run is not None
    assert run.status == "completed"
    assert run.datasource_generation == 11
    run_payload = json.loads(run.result_json)
    assert "rows" not in (run_payload.get("execution") or {})


def test_result_page_rejects_descriptor_fingerprint_that_differs_from_source_artifact(db_session):
    result_id = _add_pagination_source(db_session)
    result = db_session.get(AgentArtifactRecord, result_id)
    result.payload_json = json.dumps({**json.loads(result.payload_json), "queryFingerprint": "mismatch"})
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_page(
            result_id,
            ResultPageRequest(
                page=1,
                pageSize=20,
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "SOURCE_SQL_MISMATCH"


def test_table_result_page_uses_schema_table_source_for_derived_query(monkeypatch, db_session):
    _add_table_result_source(db_session)
    request_model = getattr(agent_module, "TableResultPageRequest", None)
    assert request_model is not None
    executed_sql: dict[str, str] = {}

    def fake_execute_query(_db, datasource_id, sql, **kwargs):
        safety_decision = kwargs["safety_decision"]
        executed_sql["datasource_id"] = datasource_id
        executed_sql["sql"] = sql
        assert safety_decision.can_execute is True
        return {
            "columns": ["id", "amount", "status"],
            "rows": [
                {"id": 1, "amount": 20, "status": "paid"},
                {"id": 2, "amount": 30, "status": "paid"},
            ],
            "latencyMs": 3,
            "warnings": [],
            "notices": [],
        }

    monkeypatch.setattr("engine.sql.executor.execute_query", fake_execute_query)

    response = agent_module.api_agent_table_result_page(
        request_model(
            datasourceId="ds-table-page",
            tableId="schema-table-page-orders",
            tableName="orders",
            page=1,
            pageSize=1,
            filters=[agent_module.ResultFilter(column="status", operator="equals", value="paid")],
            search="paid",
            sort=[agent_module.ResultSort(column="amount", direction="desc")],
        ),
        db_session,
    )

    assert response.rows == [{"id": 1, "amount": 20, "status": "paid"}]
    assert response.hasNextPage is True
    assert "FROM `dbfox`.`orders`" in executed_sql["sql"]
    assert "`status` = 'paid'" in executed_sql["sql"]
    assert "LIKE '%paid%'" in executed_sql["sql"]
    assert "ORDER BY `amount` DESC" in executed_sql["sql"]


def test_table_result_export_streams_schema_table_source(monkeypatch, db_session):
    _add_table_result_source(db_session)
    request_model = getattr(agent_module, "TableResultExportRequest", None)
    assert request_model is not None
    executed_sql: dict[str, str] = {}

    def fake_stream_rows(_self, datasource_id, sql, safety_decision, chunk_size=1000):
        executed_sql["datasource_id"] = datasource_id
        executed_sql["sql"] = sql
        assert safety_decision.can_execute is True
        yield {"id": 2, "amount": 30, "status": "paid"}
        yield {"id": 1, "amount": 20, "status": "paid"}

    monkeypatch.setattr(
        "engine.sql.execution.streaming_executor.StreamingQueryExecutor.stream_rows",
        fake_stream_rows,
    )

    response = agent_module.api_agent_table_result_export(
        request_model(
            datasourceId="ds-table-page",
            tableId="schema-table-page-orders",
            tableName="orders",
            filters=[agent_module.ResultFilter(column="status", operator="equals", value="paid")],
            search="paid",
            sort=[agent_module.ResultSort(column="amount", direction="desc")],
        ),
        db_session,
    )
    body = asyncio.run(_streaming_response_text(response))

    assert response.status_code == 200
    assert response.media_type == "text/csv"
    assert body.splitlines()[0] == "id,amount,status"
    assert "2,30,paid" in body
    assert "FROM `dbfox`.`orders`" in executed_sql["sql"]
    assert "`status` = 'paid'" in executed_sql["sql"]
    assert "LIKE '%paid%'" in executed_sql["sql"]
    assert "ORDER BY `amount` DESC" in executed_sql["sql"]
    assert "LIMIT" not in executed_sql["sql"].upper()


def test_table_result_page_returns_structured_datasource_not_found_error(db_session):
    request_model = getattr(agent_module, "TableResultPageRequest", None)
    assert request_model is not None

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_table_result_page(
            request_model(
                datasourceId="missing-ds",
                tableId="missing-table",
                tableName="orders",
                page=1,
                pageSize=20,
            ),
            db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "DATASOURCE_NOT_FOUND"
    assert "Datasource not found" in exc_info.value.detail["message"]


def test_result_page_rejects_result_view_as_source_sql_artifact(db_session):
    result_id = _add_pagination_source(db_session, artifact_id="artifact-result-page", artifact_type="result_view")

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_page(
            result_id,
            ResultPageRequest(
                page=1,
                pageSize=20,
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "SOURCE_ARTIFACT_UNSUPPORTED"


def test_result_page_uses_persisted_safe_sql_for_derived_query(monkeypatch, db_session):
    result_id = _add_pagination_source(db_session)
    executed_sql: dict[str, str] = {}

    def fake_execute_query(_db, datasource_id, sql, **kwargs):
        safety_decision = kwargs["safety_decision"]
        executed_sql["datasource_id"] = datasource_id
        executed_sql["sql"] = sql
        assert safety_decision.can_execute is True
        return {
            "columns": ["id", "amount"],
            "rows": [{"id": 1, "amount": 20}],
            "latencyMs": 3,
            "warnings": [],
            "notices": [],
        }

    monkeypatch.setattr("engine.sql.executor.execute_query", fake_execute_query)

    response = agent_module.api_agent_result_page(
        result_id,
        ResultPageRequest(
            page=1,
            pageSize=20,
            sort=[agent_module.ResultSort(column="id", direction="desc")],
        ),
        db_session,
    )

    assert response.columns == ["id", "amount"]
    assert response.rows == [{"id": 1, "amount": 20}]
    assert response.hasNextPage is False
    assert "orders" in executed_sql["sql"]
    assert "LIMIT" in executed_sql["sql"].upper()


def test_result_page_rejects_persisted_non_select_source_sql(db_session):
    result_id = _add_pagination_source(db_session, safe_sql="DELETE FROM orders")

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_page(
            result_id,
            ResultPageRequest(
                page=1,
                pageSize=20,
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "SOURCE_SQL_VALIDATION_FAILED"


def test_result_page_rejects_sort_columns_outside_source_artifact(monkeypatch, db_session):
    result_id = _add_pagination_source(db_session)

    def fail_execute_query(*_args, **_kwargs):
        raise AssertionError("sort validation must run before execution")

    monkeypatch.setattr("engine.sql.executor.execute_query", fail_execute_query)

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_page(
            result_id,
            ResultPageRequest(
                page=1,
                pageSize=20,
                sort=[agent_module.ResultSort(column="users.password", direction="asc")],
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "SORT_COLUMN_NOT_ALLOWED"


def test_result_page_applies_filters_and_search_to_derived_query(monkeypatch, db_session):
    result_id = _add_pagination_source(
        db_session,
        safe_sql="SELECT id, name, status, amount FROM orders",
        columns=["id", "name", "status", "amount"],
    )
    executed_sql: dict[str, str] = {}

    def fake_execute_query(_db, datasource_id, sql, **kwargs):
        safety_decision = kwargs["safety_decision"]
        executed_sql["datasource_id"] = datasource_id
        executed_sql["sql"] = sql
        assert safety_decision.can_execute is True
        return {
            "columns": ["id", "name", "status", "amount"],
            "rows": [{"id": 1, "name": "Acme", "status": "paid", "amount": 20}],
            "latencyMs": 3,
            "warnings": [],
            "notices": [],
        }

    monkeypatch.setattr("engine.sql.executor.execute_query", fake_execute_query)

    response = agent_module.api_agent_result_page(
        result_id,
        ResultPageRequest(
            page=1,
            pageSize=20,
            filters=[agent_module.ResultFilter(column="status", operator="equals", value="paid")],
            search="Acme",
        ),
        db_session,
    )

    sql = executed_sql["sql"]
    assert response.rows == [{"id": 1, "name": "Acme", "status": "paid", "amount": 20}]
    assert "`status` = 'paid'" in sql
    assert "LIKE '%Acme%'" in sql


def test_result_page_exact_count_uses_filtered_derived_query(monkeypatch, db_session):
    result_id = _add_pagination_source(
        db_session,
        safe_sql="SELECT id, name, status, amount FROM orders",
        columns=["id", "name", "status", "amount"],
    )
    executed_sql: list[str] = []

    def fake_execute_query(_db, datasource_id, sql, **kwargs):
        safety_decision = kwargs["safety_decision"]
        executed_sql.append(sql)
        assert datasource_id == "ds-page"
        assert safety_decision.can_execute is True
        if "COUNT" in sql.upper():
            return {
                "columns": ["count"],
                "rows": [{"count": 1}],
                "latencyMs": 2,
                "warnings": [],
                "notices": [],
            }
        return {
            "columns": ["id", "name", "status", "amount"],
            "rows": [{"id": 1, "name": "Acme", "status": "paid", "amount": 20}],
            "latencyMs": 3,
            "warnings": [],
            "notices": [],
        }

    monkeypatch.setattr("engine.sql.executor.execute_query", fake_execute_query)

    response = agent_module.api_agent_result_page(
        result_id,
        ResultPageRequest(
            page=1,
            pageSize=20,
            filters=[agent_module.ResultFilter(column="status", operator="equals", value="paid")],
            search="Acme",
            countMode="exact",
        ),
        db_session,
    )

    assert response.rowCount == 1
    assert len(executed_sql) == 2
    count_sql = executed_sql[1]
    assert "COUNT" in count_sql.upper()
    assert "`status` = 'paid'" in count_sql
    assert "LIKE '%Acme%'" in count_sql


@pytest.mark.parametrize(
    ("page", "page_size"),
    [
        (0, 20),
        (-1, 20),
        (1, 0),
        (1, 501),
    ],
)
def test_result_page_request_rejects_invalid_pagination_bounds(page, page_size):
    with pytest.raises(ValidationError):
        ResultPageRequest(
            page=page,
            pageSize=page_size,
        )


def test_result_page_rejects_filter_columns_outside_source_artifact(monkeypatch, db_session):
    result_id = _add_pagination_source(db_session)

    def fail_execute_query(*_args, **_kwargs):
        raise AssertionError("filter validation must run before execution")

    monkeypatch.setattr("engine.sql.executor.execute_query", fail_execute_query)

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_page(
            result_id,
            ResultPageRequest(
                page=1,
                pageSize=20,
                filters=[agent_module.ResultFilter(column="users.password", operator="contains", value="x")],
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "FILTER_COLUMN_NOT_ALLOWED"


def test_result_export_streams_all_matching_rows(monkeypatch, db_session):
    result_id = _add_pagination_source(
        db_session,
        safe_sql="SELECT id, created_at, status FROM orders",
        columns=["id", "created_at", "status"],
    )
    executed_sql: dict[str, str] = {}

    def fake_stream_rows(_self, datasource_id, sql, safety_decision, chunk_size=1000):
        executed_sql["datasource_id"] = datasource_id
        executed_sql["sql"] = sql
        assert safety_decision.can_execute is True
        yield {"id": 2, "created_at": "2026-06-02", "status": "paid"}
        yield {"id": 1, "created_at": "2026-06-01", "status": "paid"}

    monkeypatch.setattr(
        "engine.sql.execution.streaming_executor.StreamingQueryExecutor.stream_rows",
        fake_stream_rows,
    )

    response = agent_module.api_agent_result_export(
        result_id,
        agent_module.ResultExportRequest(
            filters=[agent_module.ResultFilter(column="status", operator="equals", value="paid")],
            search="2026",
            sort=[agent_module.ResultSort(column="created_at", direction="desc")],
        ),
        db_session,
    )
    body = asyncio.run(_streaming_response_text(response))

    assert response.status_code == 200
    assert response.media_type == "text/csv"
    assert body.splitlines()[0] == "id,created_at,status"
    assert "2026-06-02,paid" in body
    assert "`status` = 'paid'" in executed_sql["sql"]
    assert "LIKE '%2026%'" in executed_sql["sql"]
    assert "ORDER BY `created_at` DESC" in executed_sql["sql"]
    assert "LIMIT" not in executed_sql["sql"].upper()


def test_result_export_rejects_filter_columns_outside_source_artifact(monkeypatch, db_session):
    result_id = _add_pagination_source(db_session)

    def fail_execute_query(*_args, **_kwargs):
        raise AssertionError("filter validation must run before export execution")

    monkeypatch.setattr("engine.sql.executor.execute_query", fail_execute_query)

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_export(
            result_id,
            agent_module.ResultExportRequest(
                filters=[agent_module.ResultFilter(column="users.password", operator="contains", value="x")],
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "FILTER_COLUMN_NOT_ALLOWED"


async def _streaming_response_text(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
    return "".join(chunks)


def test_datasource_connection_dict() -> None:
    mock_ds = MagicMock()
    mock_ds.id = "ds_123"
    mock_ds.host = "localhost"
    mock_ds.port = 3306
    mock_ds.username = "root"
    mock_ds.database_name = "testdb"
    mock_ds.password_credential_id = "cred_datasource_password"
    mock_ds.ssh_enabled = True
    mock_ds.ssh_host = "jump"
    mock_ds.ssh_port = 22
    mock_ds.ssh_username = "sshuser"
    mock_ds.ssh_password_credential_id = "cred_ssh_password"
    mock_ds.ssh_pkey_path = "/path/to/key"
    mock_ds.ssh_key_passphrase_credential_id = "cred_ssh_key_passphrase"
    mock_ds.ssl_enabled = True
    mock_ds.ssl_ca_path = "/path/to/ca"
    mock_ds.ssl_cert_path = "/path/to/cert"
    mock_ds.ssl_key_path = "/path/to/key"
    mock_ds.ssl_verify_identity = True

    config = datasource_connection_dict(mock_ds)
    assert config["id"] == "ds_123"
    assert config["host"] == "localhost"
    assert config["port"] == 3306
    assert config["username"] == "root"
    assert config["database_name"] == "testdb"
    assert config["password_credential_id"] == "cred_datasource_password"
    assert config["ssh_enabled"] is True
    assert config["ssh_host"] == "jump"
    assert config["ssh_port"] == 22
    assert config["ssh_username"] == "sshuser"
    assert config["ssh_password_credential_id"] == "cred_ssh_password"
    assert config["ssh_pkey_path"] == "/path/to/key"
    assert config["ssh_key_passphrase_credential_id"] == "cred_ssh_key_passphrase"
    assert config["ssl_enabled"] is True
    assert config["ssl_ca_path"] == "/path/to/ca"
    assert config["ssl_cert_path"] == "/path/to/cert"
    assert config["ssl_key_path"] == "/path/to/key"
    assert config["ssl_verify_identity"] is True


def test_project_id_resolution_fallback(db_session) -> None:
    # Test fallback to default project when project_id is None or empty or DEFAULT_PROJECT_ID
    pid1 = resolve_project_id(db_session, None)
    pid2 = resolve_project_id(db_session, "")
    pid3 = resolve_project_id(db_session, DEFAULT_PROJECT_ID)
    
    assert pid1 == DEFAULT_PROJECT_ID
    assert pid2 == DEFAULT_PROJECT_ID
    assert pid3 == DEFAULT_PROJECT_ID
    
    # Verify default project actually exists in db
    proj = db_session.query(Project).filter(Project.id == DEFAULT_PROJECT_ID).first()
    assert proj is not None
    assert proj.status == "active"


def test_console_unexpected_error_never_leaks_exception_text(monkeypatch, db_session, caplog) -> None:
    _add_console_datasource(db_session, datasource_id="ds-console-boundary")
    sentinel = "console-execution-secret-sentinel"

    def fail_policy(*_args, **_kwargs):
        raise RuntimeError(f"database password={sentinel}")

    monkeypatch.setattr(
        agent_module.PolicyEngine,
        "enforce_query_policy",
        staticmethod(fail_policy),
    )

    capture_logger = logging.Logger("test.agent_console_boundary")
    capture_logger.setLevel(logging.ERROR)
    capture_logger.propagate = False
    capture_logger.addHandler(caplog.handler)
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(agent_module, "logger", capture_logger)
            with pytest.raises(HTTPException) as exc_info:
                agent_module.api_agent_console_execute(
                    agent_module.ConsoleExecuteRequest(
                        datasourceId="ds-console-boundary",
                        sql="SELECT 1",
                    ),
                    db_session,
                )
    finally:
        capture_logger.removeHandler(caplog.handler)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "CONSOLE_EXECUTION_ERROR",
        "message": "The SQL Console request could not be completed.",
    }
    assert sentinel not in repr(exc_info.value.detail)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "agent_sql_console_execution" in caplog.text


def test_result_page_unexpected_error_never_leaks_exception_text(monkeypatch, db_session, caplog) -> None:
    result_id = _add_pagination_source(db_session, artifact_id="artifact-boundary-page")
    sentinel = "result-page-secret-sentinel"

    def fail_page(_self, _query):
        raise RuntimeError(f"driver authorization={sentinel}")

    monkeypatch.setattr(agent_module.ResultViewService, "page", fail_page)

    capture_logger = logging.Logger("test.agent_result_page_boundary")
    capture_logger.setLevel(logging.ERROR)
    capture_logger.propagate = False
    capture_logger.addHandler(caplog.handler)
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(agent_module, "logger", capture_logger)
            with pytest.raises(HTTPException) as exc_info:
                agent_module.api_agent_result_page(
                    result_id,
                    ResultPageRequest(
                        page=1,
                        pageSize=20,
                    ),
                    db_session,
                )
    finally:
        capture_logger.removeHandler(caplog.handler)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "RESULT_PAGE_ERROR",
        "message": "The result page could not be retrieved.",
    }
    assert sentinel not in repr(exc_info.value.detail)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "agent_result_page" in caplog.text


def test_result_view_error_never_leaks_its_code_or_message(monkeypatch, db_session) -> None:
    from engine.sql.result_view.models import ResultViewError

    result_id = _add_pagination_source(db_session, artifact_id="artifact-boundary-result-view")
    sentinel = "result-view-error-secret-sentinel"

    def fail_page(_self, _query):
        raise ResultViewError(
            f"caller-code-{sentinel}",
            f"driver authorization={sentinel}",
            status_code=400,
        )

    monkeypatch.setattr(agent_module.ResultViewService, "page", fail_page)

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_page(
            result_id,
            ResultPageRequest(
                page=1,
                pageSize=20,
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {
        "code": "RESULT_PAGE_ERROR",
        "message": "The result page could not be retrieved.",
    }
    assert sentinel not in repr(exc_info.value.detail)
