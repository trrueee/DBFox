import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import engine.api.agent_results as result_module
from engine.agent.resource_refs import dump_resource_refs
from engine.agent.artifact_view import (
    ArtifactCsvStream,
    ArtifactTablePage,
)
from engine.dlc.snapshot import (
    ArtifactContractContribution,
    ArtifactTableViewContribution,
    RuntimeContributionSnapshot,
)
from engine.runtime_composition import (
    active_runtime_snapshot,
    set_active_runtime_snapshot,
)
from dlcs.dbfox_data.backend.artifact_contracts import ResultViewArtifactPayload
from engine.api.agent_results import ResultPageRequest
from engine.resource import ResourceScopeRef
from engine.models import (
    AgentArtifactRecord,
    AgentRun,
    AgentSession,
    AgentSessionInput,
    DataSource,
    SchemaColumn,
    SchemaTable,
    SecurityAuditRecord,
)
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
        title="Page",
        created_at=now,
        updated_at=now,
    )
    input_row = AgentSessionInput(
        id="input-page",
        session_id=session.id,
        run_id="run-page",
        sequence=1,
        idempotency_key="input-page",
        content="Orders",
        resource_refs_json=dump_resource_refs(
            (ResourceScopeRef(kind="dbfox.data.database", id=datasource.id, version=1),)
        ),
    )
    run = AgentRun(
        id="run-page",
        session_id="conv-page",
        input_id=input_row.id,
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
        presentation_json=json.dumps(
            {"mode": "both", "priority": 1, "collapsed": False}
        ),
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
    db_session.add(input_row)
    db_session.flush()
    db_session.add(run)
    db_session.flush()
    db_session.add(artifact)
    db_session.flush()
    result_id = f"result-for-{artifact_id}"
    db_session.add(
        AgentArtifactRecord(
            id=result_id,
            run_id="run-page",
            session_id="conv-page",
            semantic_id="result_view",
            type="result_view",
            title="Orders result",
            payload_json=json.dumps(
                {
                    "sourceSqlArtifactId": artifact_id,
                    "queryFingerprint": result_source_fingerprint(safe_sql, "mysql"),
                    "datasourceGeneration": 1,
                    "columns": columns or ["id", "amount"],
                }
            ),
            presentation_json="{}",
            depends_on_json=json.dumps([artifact_id]),
            refs_json="{}",
            relations_json=json.dumps(
                [{"relation": "derived_from", "artifact_id": artifact_id}]
            ),
            status="completed",
            sequence=2,
            created_at=now,
        )
    )
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
        SchemaColumn(
            id="schema-col-page-id",
            table_id=table_id,
            column_name="id",
            data_type="integer",
            ordinal_position=1,
        ),
        SchemaColumn(
            id="schema-col-page-amount",
            table_id=table_id,
            column_name="amount",
            data_type="decimal",
            ordinal_position=2,
        ),
        SchemaColumn(
            id="schema-col-page-status",
            table_id=table_id,
            column_name="status",
            data_type="text",
            ordinal_position=3,
        ),
    ]
    db_session.add_all([datasource, table, *columns])
    db_session.commit()


class _CapturedDurableTableView:
    def __init__(self) -> None:
        self.page_request = None
        self.export_request = None

    def page(self, artifact, request):
        self.page_request = request
        return ArtifactTablePage(
            columns=["id", "amount"],
            rows=[{"id": "2", "amount": "40"}],
            page=request.page,
            page_size=request.page_size,
            row_count=1,
            has_next_page=False,
            latency_ms=0,
            original_executed_at="2026-08-23T08:00:00Z",
            read_at="2026-08-23T08:01:00Z",
            read_id="read-api",
            resource_version=str(artifact.resource_refs[0].version),
            query_fingerprint=str(artifact.payload["queryFingerprint"]),
            notices=["durable"],
        )

    def export_csv(self, _artifact, request):
        self.export_request = request
        return ArtifactCsvStream(
            chunks=iter(("id,amount\n", "2,40\n")),
            row_count=1,
            source_truncated=False,
        )


def _durable_table_snapshot(provider) -> RuntimeContributionSnapshot:
    return RuntimeContributionSnapshot(
        snapshot_id="snapshot-artifact-table-api",
        active_dlcs=(),
        tools=(),
        resource_providers=(),
        resource_resolvers=(),
        context_contributors=(),
        completion_constraints=(),
        completion_supports=(),
        artifact_contracts=(
            ArtifactContractContribution(
                artifact_type="dbfox.data.result_view",
                schema_version=1,
                validator=ResultViewArtifactPayload,
                owner_id="dbfox.data",
            ),
        ),
        operations=(),
        artifact_table_views=(
            ArtifactTableViewContribution(
                artifact_type="dbfox.data.result_view",
                provider=provider,
                owner_id="dbfox.data",
            ),
        ),
    )


def test_artifact_page_and_export_dispatch_to_durable_capability_view(
    db_session,
) -> None:
    result_id = _add_pagination_source(db_session)
    result = db_session.get(AgentArtifactRecord, result_id)
    assert result is not None
    result.type = "dbfox.data.result_view"
    result.payload_ref = "data_result_api"
    result.resource_refs_json = dump_resource_refs(
        (ResourceScopeRef(kind="dbfox.data.database", id="ds-page", version=1),)
    )
    result.payload_json = json.dumps(
        {
            "sourceSqlArtifactId": "artifact-sql-page",
            "queryFingerprint": result_source_fingerprint(
                "SELECT id, amount FROM orders", "mysql"
            ),
            "datasourceGeneration": 1,
            "columns": ["id", "amount"],
            "rowCount": 1,
            "returnedRows": 1,
            "latencyMs": 2,
            "executedAt": "2026-08-23T08:00:00Z",
            "truncated": False,
            "evidenceKind": "query_result",
        }
    )
    db_session.commit()

    provider = _CapturedDurableTableView()
    previous = active_runtime_snapshot()
    set_active_runtime_snapshot(_durable_table_snapshot(provider))
    try:
        page = result_module.api_agent_result_page(
            result_id,
            ResultPageRequest(
                page=1,
                pageSize=50,
                filters=[ResultFilter(column="amount", operator="gte", value=25)],
                sort=[ResultSort(column="amount", direction="desc")],
            ),
            db_session,
        )
        exported = result_module.api_agent_result_export(
            result_id,
            result_module.ResultExportRequest(search="40"),
            db_session,
        )
        body = asyncio.run(_streaming_response_text(exported))
    finally:
        set_active_runtime_snapshot(previous)

    assert page.consistency == "durable_snapshot"
    assert page.rows == [{"id": "2", "amount": "40"}]
    assert page.datasourceGeneration == "1"
    assert provider.page_request.filters[0].column == "amount"
    assert provider.page_request.sort[0].direction == "desc"
    assert provider.export_request.search == "40"
    assert body == "id,amount\n2,40\n"
    assert exported.headers["x-dbfox-export-row-count"] == "1"


def test_table_result_page_uses_schema_table_source_for_derived_query(
    monkeypatch, db_session
):
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

    def fake_stream_rows(
        _self, datasource_id, sql, safety_decision, chunk_size=1000, **_kwargs
    ):
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
    audit = (
        db_session.query(SecurityAuditRecord)
        .filter_by(
            action="table.result.export",
            resource_id="schema-table-page-orders",
        )
        .one()
    )
    assert audit.outcome == "requested"
    assert "paid" not in audit.details_json


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
            "filters": [{"column": "status", "operator": "equals", "value": "paid"}]
            * 17,
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
            "filters": [{"column": "status", "operator": "unknown", "value": "paid"}],
        },
    ],
)
def test_result_page_request_rejects_unbounded_query_inputs(payload):
    with pytest.raises(ValidationError):
        ResultPageRequest.model_validate(payload)


async def _streaming_response_text(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
    return "".join(chunks)
