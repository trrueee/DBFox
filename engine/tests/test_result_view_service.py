from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from engine.models import AgentArtifactRecord, AgentRun, AgentSession, DataSource, SchemaColumn, SchemaTable
from engine.sql.result_view import models as result_view_models
from engine.sql.result_view.models import (
    ResultExportQuery,
    ResultFilter,
    ResultPageQuery,
    ResultViewError,
    ResultSourceRef,
    ResultSort,
    TableSourceRef,
)
from engine.sql.result_view.service import ResultViewService
from engine.sql.result_view.fingerprint import result_source_fingerprint


def _add_result_source(
    db_session,
    *,
    datasource_id: str = "ds-result-service",
    artifact_id: str = "artifact-sql-result-service",
    artifact_type: str = "sql",
    safe_sql: str = "SELECT id, created_at, status FROM orders",
    columns: list[object] | None = None,
) -> str:
    now = datetime.now(UTC)
    datasource = DataSource(
        id=datasource_id,
        name="Result Service DS",
        db_type="mysql",
        host="localhost",
        port=3306,
        database_name="dbfox",
        username="root",
        connection_generation=1,
    )
    session = AgentSession(
        id=f"conv-{artifact_id}",
        datasource_id=datasource_id,
        title="Result service",
        context_tables_json="[]",
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id=f"run-{artifact_id}",
        session_id=session.id,
        datasource_id=datasource_id,
        datasource_generation=1,
        llm_credential_id="credential-result-service",
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
        run_id=run.id,
        session_id=session.id,
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
        depends_on_json=json.dumps(["sql_candidate"]),
        refs_json="{}",
        relations_json="[]",
        status="completed",
        sequence=1,
        created_at=now,
    )
    # These records intentionally reference one another by IDs instead of ORM
    # relationships. Flush each FK parent explicitly so the fixture exercises
    # the same constraints as production without relying on UoW insert order.
    db_session.add(datasource)
    db_session.flush()
    db_session.add(session)
    db_session.flush()
    db_session.add(run)
    db_session.flush()
    db_session.add(artifact)
    db_session.flush()
    result_id = f"result-{artifact_id}"
    db_session.add(AgentArtifactRecord(
        id=result_id,
        run_id=run.id,
        session_id=session.id,
        semantic_id="result_view",
        type="result_view",
        title="Orders result",
        payload_json=json.dumps({
            "sourceSqlArtifactId": artifact_id,
            "queryFingerprint": result_source_fingerprint(safe_sql, "mysql"),
            "datasourceGeneration": 1,
            "executedAt": "2026-07-20T00:00:00+00:00",
            "columns": columns or [
                {"name": "id", "type": "integer"},
                {"name": "created_at", "type": "datetime"},
                {"name": "status", "type": "text"},
            ],
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


def _add_table_source(
    db_session,
    *,
    datasource_id: str = "ds-table-service",
    table_id: str = "schema-table-orders",
    table_name: str = "orders",
    table_schema: str = "dbfox",
) -> None:
    datasource = db_session.get(DataSource, datasource_id) or DataSource(
        id=datasource_id,
        name="Table Service DS",
        db_type="mysql",
        host="localhost",
        port=3306,
        database_name="dbfox",
        username="root",
    )
    table = SchemaTable(
        id=table_id,
        data_source_id=datasource_id,
        table_schema=table_schema,
        table_name=table_name,
        table_type="BASE TABLE",
    )
    columns = [
        SchemaColumn(id=f"{table_id}-col-id", table_id=table_id, column_name="id", data_type="integer", ordinal_position=1),
        SchemaColumn(
            id=f"{table_id}-col-created",
            table_id=table_id,
            column_name="created_at",
            data_type="datetime",
            ordinal_position=2,
        ),
        SchemaColumn(id=f"{table_id}-col-status", table_id=table_id, column_name="status", data_type="text", ordinal_position=3),
    ]
    db_session.add_all([datasource, table, *columns])
    db_session.commit()


def test_result_view_service_compiles_page_count_and_export_from_same_query(db_session) -> None:
    result_id = _add_result_source(db_session)
    executed_sql: list[str] = []

    def fake_execute_query(_db, datasource_id, sql, **kwargs):
        executed_sql.append(sql)
        assert datasource_id == "ds-result-service"
        assert kwargs["safety_decision"].can_execute is True
        if "COUNT" in sql.upper():
            return {"columns": ["count"], "rows": [{"count": 2}], "latencyMs": 1}
        return {
            "columns": ["id", "created_at", "status"],
            "rows": [
                {"id": 2, "created_at": "2026-06-02", "status": "paid"},
                {"id": 1, "created_at": "2026-06-01", "status": "paid"},
            ],
            "latencyMs": 3,
            "warnings": [],
            "notices": [],
        }

    service = ResultViewService(db_session, row_executor=fake_execute_query)
    source = ResultSourceRef(artifact_id=result_id)
    page = service.page(
        ResultPageQuery(
            source=source,
            filters=[ResultFilter(column="status", operator="equals", value="paid")],
            search="2026",
            sort=[ResultSort(column="created_at", direction="desc")],
            page=1,
            page_size=1,
            count_mode="exact",
        )
    )

    export_sql = service.build_export_sql(
        ResultExportQuery(
            source=source,
            filters=[ResultFilter(column="status", operator="equals", value="paid")],
            search="2026",
            sort=[ResultSort(column="created_at", direction="desc")],
        )
    )

    assert page.row_count == 2
    assert page.has_next_page is True
    assert page.rows == [{"id": 2, "created_at": "2026-06-02", "status": "paid"}]
    assert page.consistency == "live_reexecution"
    assert page.original_executed_at == "2026-07-20T00:00:00+00:00"
    assert page.view_executed_at != page.original_executed_at
    assert page.view_execution_id.startswith("view_")
    assert page.datasource_generation == 1
    assert page.query_fingerprint == result_source_fingerprint(
        "SELECT id, created_at, status FROM orders", "mysql"
    )
    assert len(executed_sql) == 2
    page_sql = executed_sql[0]
    count_sql = executed_sql[1]
    assert "`status` = 'paid'" in page_sql
    assert "LIKE '%2026%'" in page_sql
    assert "ORDER BY `created_at` DESC" in page_sql
    assert "LIMIT" in page_sql.upper()
    assert "COUNT" in count_sql.upper()
    assert "`status` = 'paid'" in count_sql
    assert "LIKE '%2026%'" in count_sql
    assert "ORDER BY `created_at` DESC" in export_sql
    assert "LIMIT" not in export_sql.upper()


def test_exact_count_diagnostic_never_logs_sql_or_exception_text(db_session, caplog) -> None:
    sql_secret = "SELECT id, token FROM orders WHERE token = 'result-view-sql-secret'"
    exception_secret = "result-view-driver-secret"
    result_id = _add_result_source(db_session, artifact_id="artifact-private-log", safe_sql=sql_secret)

    def fake_execute_query(_db, _datasource_id, sql, **_kwargs):
        if "COUNT" in sql.upper():
            raise RuntimeError(exception_secret)
        return {
            "columns": ["id", "token"],
            "rows": [{"id": 1, "token": "redacted"}],
            "latencyMs": 1,
            "warnings": [],
            "notices": [],
        }

    service = ResultViewService(db_session, row_executor=fake_execute_query)
    source = ResultSourceRef(artifact_id=result_id)
    with caplog.at_level(logging.WARNING, logger="dbfox.sql.result_view"):
        page = service.page(ResultPageQuery(source=source, page=1, page_size=10, count_mode="exact"))

    assert page.row_count is None
    assert sql_secret not in caplog.text
    assert exception_secret not in caplog.text
    assert "code=result_view_exact_count" in caplog.text
    assert "type=RuntimeError" in caplog.text
    assert "fingerprint=" in caplog.text


def test_result_view_service_pages_database_table_through_sql_backed_compiler(db_session) -> None:
    _add_table_source(db_session)
    table_source_ref = getattr(result_view_models, "TableSourceRef", None)
    table_page_query = getattr(result_view_models, "TablePageQuery", None)
    assert table_source_ref is not None
    assert table_page_query is not None

    executed_sql: list[str] = []

    def fake_execute_query(_db, datasource_id, sql, **kwargs):
        executed_sql.append(sql)
        assert datasource_id == "ds-table-service"
        assert kwargs["safety_decision"].can_execute is True
        if "COUNT" in sql.upper():
            return {"columns": ["count"], "rows": [{"count": 2}], "latencyMs": 1}
        return {
            "columns": ["id", "created_at", "status"],
            "rows": [
                {"id": 2, "created_at": "2026-06-02", "status": "paid"},
                {"id": 1, "created_at": "2026-06-01", "status": "paid"},
            ],
            "latencyMs": 3,
            "warnings": [],
            "notices": [],
        }

    service = ResultViewService(db_session, row_executor=fake_execute_query)
    page = service.page_table(
        table_page_query(
            source=table_source_ref(datasource_id="ds-table-service", table_id="schema-table-orders", table_name="orders"),
            filters=[ResultFilter(column="status", operator="equals", value="paid")],
            search="2026",
            sort=[ResultSort(column="created_at", direction="desc")],
            page=1,
            page_size=1,
            count_mode="exact",
        )
    )

    assert page.row_count == 2
    assert page.has_next_page is True
    assert page.rows == [{"id": 2, "created_at": "2026-06-02", "status": "paid"}]
    page_sql = executed_sql[0]
    count_sql = executed_sql[1]
    assert "FROM `dbfox`.`orders`" in page_sql
    assert "`status` = 'paid'" in page_sql
    assert "LIKE '%2026%'" in page_sql
    assert "ORDER BY `created_at` DESC" in page_sql
    assert "LIMIT" in page_sql.upper()
    assert "COUNT" in count_sql.upper()


def test_result_view_service_uses_table_id_to_disambiguate_same_named_tables(db_session) -> None:
    _add_table_source(
        db_session,
        datasource_id="ds-multi-schema",
        table_id="schema-public-orders",
        table_name="orders",
        table_schema="public",
    )
    _add_table_source(
        db_session,
        datasource_id="ds-multi-schema",
        table_id="schema-analytics-orders",
        table_name="orders",
        table_schema="analytics",
    )
    executed_sql: list[str] = []

    def fake_execute_query(_db, datasource_id, sql, **kwargs):
        executed_sql.append(sql)
        assert datasource_id == "ds-multi-schema"
        assert kwargs["safety_decision"].can_execute is True
        return {
            "columns": ["id", "created_at", "status"],
            "rows": [{"id": 1, "created_at": "2026-06-01", "status": "paid"}],
            "latencyMs": 3,
            "warnings": [],
            "notices": [],
        }

    service = ResultViewService(db_session, row_executor=fake_execute_query)
    page = service.page_table(
        result_view_models.TablePageQuery(
            source=TableSourceRef(
                datasource_id="ds-multi-schema",
                table_id="schema-analytics-orders",
                table_name="orders",
            ),
            page=1,
            page_size=20,
        )
    )

    assert page.rows == [{"id": 1, "created_at": "2026-06-01", "status": "paid"}]
    assert "FROM `analytics`.`orders`" in executed_sql[0]
    assert "FROM `public`.`orders`" not in executed_sql[0]


def test_result_view_service_rejects_result_view_as_source_sql_artifact(db_session) -> None:
    result_id = _add_result_source(db_session, artifact_id="artifact-result-service", artifact_type="result_view")
    service = ResultViewService(db_session, row_executor=lambda *_args, **_kwargs: {})
    source = ResultSourceRef(artifact_id=result_id)

    try:
        service.load_verified_source(source)
    except ResultViewError as exc:
        assert exc.code == "SOURCE_ARTIFACT_UNSUPPORTED"
    else:
        raise AssertionError("result_view artifacts must not be accepted as source SQL artifacts")


def test_result_view_service_rejects_artifact_after_datasource_generation_changes(db_session) -> None:
    result_id = _add_result_source(db_session, artifact_id="artifact-stale-generation")
    datasource = db_session.get(DataSource, "ds-result-service")
    assert datasource is not None
    datasource.connection_generation = 2
    db_session.commit()

    service = ResultViewService(
        db_session,
        row_executor=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("stale artifact SQL must never execute")
        ),
    )
    source = ResultSourceRef(artifact_id=result_id)

    try:
        service.page(ResultPageQuery(source=source, page=1, page_size=10))
    except ResultViewError as exc:
        assert exc.code == "SOURCE_DATASOURCE_CHANGED"
        assert exc.status_code == 409
    else:
        raise AssertionError("stale source artifacts must be rejected")


def test_result_gateway_requires_a_single_derived_from_relation(db_session) -> None:
    result_id = _add_result_source(db_session, artifact_id="artifact-relation-required")
    result = db_session.get(AgentArtifactRecord, result_id)
    assert result is not None
    result.relations_json = "[]"
    db_session.commit()

    try:
        ResultViewService(db_session).load_verified_source(ResultSourceRef(artifact_id=result_id))
    except ResultViewError as exc:
        assert exc.code == "SOURCE_ARTIFACT_NOT_FOUND"
    else:
        raise AssertionError("descriptor-only result sources must be rejected")


def test_result_gateway_rejects_descriptor_relation_mismatch(db_session) -> None:
    result_id = _add_result_source(db_session, artifact_id="artifact-relation-mismatch")
    result = db_session.get(AgentArtifactRecord, result_id)
    assert result is not None
    payload = json.loads(str(result.payload_json))
    payload["sourceSqlArtifactId"] = "artifact-other"
    result.payload_json = json.dumps(payload)
    db_session.commit()

    try:
        ResultViewService(db_session).load_verified_source(ResultSourceRef(artifact_id=result_id))
    except ResultViewError as exc:
        assert exc.code == "SOURCE_SQL_MISMATCH"
    else:
        raise AssertionError("descriptor and relation must identify the same SQL Artifact")


def test_chart_data_reruns_the_result_source_without_persisting_series(db_session) -> None:
    result_id = _add_result_source(
        db_session,
        artifact_id="artifact-chart-source",
        safe_sql="SELECT category, amount FROM orders LIMIT 1000",
        columns=[{"name": "category", "type": "text"}, {"name": "amount", "type": "integer"}],
    )
    result = db_session.get(AgentArtifactRecord, result_id)
    assert result is not None
    chart = AgentArtifactRecord(
        id="artifact-chart-data",
        run_id=result.run_id,
        session_id=result.session_id,
        semantic_id="chart_orders",
        type="chart",
        title="Orders by category",
        payload_json=json.dumps({
            "sourceResultArtifactId": result_id,
            "chartType": "bar",
            "x": "category",
            "y": ["amount"],
            "aggregation": "sum",
        }),
        presentation_json="{}",
        depends_on_json=json.dumps([result_id]),
        refs_json="{}",
        relations_json=json.dumps([{"relation": "derived_from", "artifact_id": result_id}]),
        status="completed",
        sequence=3,
        created_at=datetime.now(UTC),
    )
    db_session.add(chart)
    db_session.commit()

    class FakeStreamingExecutor:
        def stream_rows(self, datasource_id, sql, decision, **_kwargs):
            assert datasource_id == "ds-result-service"
            assert sql == "SELECT category, amount FROM orders LIMIT 1000"
            assert decision.can_execute is True
            yield {"category": "A", "amount": 10}
            yield {"category": "A", "amount": 5}
            yield {"category": "B", "amount": 7}

    data = ResultViewService(db_session, streaming_executor=FakeStreamingExecutor()).chart_data(chart.id)

    assert data.series == [{"label": "A", "value": 15.0}, {"label": "B", "value": 7.0}]
    assert data.sample_size == 3
    assert data.truncated is False
    assert "series" not in json.loads(chart.payload_json)
