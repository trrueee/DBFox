from __future__ import annotations

import json
from datetime import UTC, datetime

from engine.models import AgentArtifactRecord, AgentRun, AgentSession, DataSource
from engine.sql.result_view.models import (
    ResultExportQuery,
    ResultFilter,
    ResultPageQuery,
    ResultSourceRef,
    ResultSort,
)
from engine.sql.result_view.service import ResultViewService
from engine.sql.execution.csv_export import CsvExportService, escape_csv_cell


def _add_result_source(
    db_session,
    *,
    datasource_id: str = "ds-result-service",
    artifact_id: str = "artifact-result-service",
    safe_sql: str = "SELECT id, created_at, status FROM orders",
    columns: list[object] | None = None,
) -> None:
    now = datetime.now(UTC)
    datasource = DataSource(
        id=datasource_id,
        name="Result Service DS",
        db_type="mysql",
        host="localhost",
        port=3306,
        database_name="dbfox",
        username="root",
        password_ciphertext="cipher",
        password_nonce="nonce",
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
        question="Orders",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    artifact = AgentArtifactRecord(
        id=artifact_id,
        run_id=run.id,
        session_id=session.id,
        semantic_id=f"semantic-{artifact_id}",
        type="result_view",
        title="Orders result",
        payload_json=json.dumps(
            {
                "safeSql": safe_sql,
                "dialect": "mysql",
                "columns": columns
                or [
                    {"name": "id", "type": "integer"},
                    {"name": "created_at", "type": "datetime"},
                    {"name": "status", "type": "text"},
                ],
            }
        ),
        presentation_json=json.dumps({"mode": "both", "priority": 1, "collapsed": False}),
        depends_on_json=json.dumps(["sql_candidate"]),
        status="completed",
        sequence=1,
        created_at=now,
    )
    db_session.add_all([datasource, session, run, artifact])
    db_session.commit()


def test_result_view_service_compiles_page_count_and_export_from_same_query(db_session) -> None:
    _add_result_source(db_session)
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
    source = ResultSourceRef(
        datasource_id="ds-result-service",
        source_sql_artifact_id="artifact-result-service",
        safe_sql="SELECT id, created_at, status FROM orders",
    )
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


def test_csv_export_service_streams_and_escapes_formula_cells() -> None:
    assert escape_csv_cell(None) == ""
    assert escape_csv_cell("=1+1") == "'=1+1"
    assert escape_csv_cell("+cmd") == "'+cmd"
    assert escape_csv_cell("-10") == "'-10"
    assert escape_csv_cell("@user") == "'@user"
    assert escape_csv_cell("safe") == "safe"

    rows = iter(
        [
            {"name": "=SUM(1,2)", "note": "@cmd"},
            {"name": "Alice", "note": None},
        ]
    )
    chunks = list(CsvExportService.stream_csv(rows, ["name", "note"]))
    body = "".join(chunks)

    assert chunks[0] == "name,note\n"
    assert "\"'=SUM(1,2)\",'@cmd" in body
    assert "Alice,\n" in body
