import asyncio
import json
import logging
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import engine.api.agent_results as result_module
from engine.api.agent_results import ResultPageRequest
from engine.models import AgentArtifactRecord, AgentRun, AgentSession, DataSource, SchemaColumn, SchemaTable
from engine.sql.result_view.fingerprint import result_source_fingerprint
from engine.sql.result_view.models import ResultFilter, ResultSort

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
def test_result_page_rejects_descriptor_fingerprint_that_differs_from_source_artifact(db_session):
    result_id = _add_pagination_source(db_session)
    result = db_session.get(AgentArtifactRecord, result_id)
    result.payload_json = json.dumps({**json.loads(result.payload_json), "queryFingerprint": "mismatch"})
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        result_module.api_agent_result_page(
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

    response = result_module.api_agent_table_result_page(
        result_module.TableResultPageRequest(
            datasourceId="ds-table-page",
            tableId="schema-table-page-orders",
            tableName="orders",
            page=1,
            pageSize=1,
            filters=[ResultFilter(column="status", operator="equals", value="paid")],
            search="paid",
            sort=[ResultSort(column="amount", direction="desc")],
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

    response = result_module.api_agent_table_result_export(
        result_module.TableResultExportRequest(
            datasourceId="ds-table-page",
            tableId="schema-table-page-orders",
            tableName="orders",
            filters=[ResultFilter(column="status", operator="equals", value="paid")],
            search="paid",
            sort=[ResultSort(column="amount", direction="desc")],
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
    with pytest.raises(HTTPException) as exc_info:
        result_module.api_agent_table_result_page(
            result_module.TableResultPageRequest(
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
        result_module.api_agent_result_page(
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

    response = result_module.api_agent_result_page(
        result_id,
        ResultPageRequest(
            page=1,
            pageSize=20,
            sort=[ResultSort(column="id", direction="desc")],
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
        result_module.api_agent_result_page(
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
        result_module.api_agent_result_page(
            result_id,
            ResultPageRequest(
                page=1,
                pageSize=20,
                sort=[ResultSort(column="users.password", direction="asc")],
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

    response = result_module.api_agent_result_page(
        result_id,
        ResultPageRequest(
            page=1,
            pageSize=20,
            filters=[ResultFilter(column="status", operator="equals", value="paid")],
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

    response = result_module.api_agent_result_page(
        result_id,
        ResultPageRequest(
            page=1,
            pageSize=20,
            filters=[ResultFilter(column="status", operator="equals", value="paid")],
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


@pytest.mark.parametrize(
    "payload",
    [
        {"page": 1, "pageSize": 20, "search": "x" * 513},
        {
            "page": 1,
            "pageSize": 20,
            "filters": [
                {"column": "status", "operator": "equals", "value": "paid"}
            ] * 17,
        },
        {
            "page": 1,
            "pageSize": 20,
            "filters": [
                {"column": "status", "operator": "equals", "value": "x" * 4097}
            ],
        },
        {
            "page": 1,
            "pageSize": 20,
            "filters": [
                {"column": "status", "operator": "unknown", "value": "paid"}
            ],
        },
    ],
)
def test_result_page_request_rejects_unbounded_query_inputs(payload):
    with pytest.raises(ValidationError):
        ResultPageRequest.model_validate(payload)


def test_result_page_rejects_filter_columns_outside_source_artifact(monkeypatch, db_session):
    result_id = _add_pagination_source(db_session)

    def fail_execute_query(*_args, **_kwargs):
        raise AssertionError("filter validation must run before execution")

    monkeypatch.setattr("engine.sql.executor.execute_query", fail_execute_query)

    with pytest.raises(HTTPException) as exc_info:
        result_module.api_agent_result_page(
            result_id,
            ResultPageRequest(
                page=1,
                pageSize=20,
                filters=[ResultFilter(column="users.password", operator="contains", value="x")],
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

    response = result_module.api_agent_result_export(
        result_id,
        result_module.ResultExportRequest(
            filters=[ResultFilter(column="status", operator="equals", value="paid")],
            search="2026",
            sort=[ResultSort(column="created_at", direction="desc")],
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
        result_module.api_agent_result_export(
            result_id,
            result_module.ResultExportRequest(
                filters=[ResultFilter(column="users.password", operator="contains", value="x")],
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


def test_result_page_unexpected_error_never_leaks_exception_text(monkeypatch, db_session, caplog) -> None:
    result_id = _add_pagination_source(db_session, artifact_id="artifact-boundary-page")
    sentinel = "result-page-secret-sentinel"

    def fail_page(_self, _query):
        raise RuntimeError(f"driver authorization={sentinel}")

    monkeypatch.setattr(result_module.ResultViewService, "page", fail_page)

    capture_logger = logging.Logger("test.agent_result_page_boundary")
    capture_logger.setLevel(logging.ERROR)
    capture_logger.propagate = False
    capture_logger.addHandler(caplog.handler)
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(result_module, "logger", capture_logger)
            with pytest.raises(HTTPException) as exc_info:
                result_module.api_agent_result_page(
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

    monkeypatch.setattr(result_module.ResultViewService, "page", fail_page)

    with pytest.raises(HTTPException) as exc_info:
        result_module.api_agent_result_page(
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
