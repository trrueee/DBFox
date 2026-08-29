import asyncio
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import engine.api.agent_results as result_module
from engine.agent.resource_refs import dump_resource_refs
from engine.representation import (
    DATAFRAME_REPRESENTATION_TYPE,
    ArtifactRepresentationDescriptor,
    ArtifactRepresentationOperation,
    ArtifactRepresentationRequest,
    ArtifactRepresentationResult,
    ArtifactRepresentationStream,
    DataFrameField,
    DataFrameFilter,
    DataFramePage,
    DataFramePageRequest,
    DataFrameSort,
)
from engine.dlc.snapshot import (
    ArtifactContractContribution,
    ArtifactRepresentationContribution,
    RuntimeContributionSnapshot,
)
from engine.runtime_composition import (
    active_runtime_snapshot,
    set_active_runtime_snapshot,
)
from dlcs.dbfox_data.backend.artifact_contracts import (
    SnapshotBackedResultViewArtifactPayload,
)
from engine.resource import ResourceScopeRef
from engine.models import (
    AgentArtifactRecord,
    AgentRun,
    AgentSession,
    AgentSessionInput,
)
from dlcs.dbfox_data.backend.query_identity import query_fingerprint


def _query_fingerprint(safe_sql: str) -> str:
    return query_fingerprint(
        ResourceScopeRef(kind="dbfox.data.database", id="ds-page", version=1),
        safe_sql,
    )


def _add_pagination_source(
    db_session,
    *,
    artifact_id: str = "artifact-sql-page",
    artifact_type: str = "dbfox.data.sql",
    safe_sql: str = "SELECT id, amount FROM orders",
    columns: list[str] | None = None,
) -> str:
    now = datetime.now(UTC)
    datasource_id = "ds-page"
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
            (ResourceScopeRef(kind="dbfox.data.database", id=datasource_id, version=1),)
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
                "queryFingerprint": _query_fingerprint(safe_sql),
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
                    "queryFingerprint": _query_fingerprint(safe_sql),
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


class _CapturedDataFrameRepresentation:
    def __init__(self) -> None:
        self.page_request = None
        self.export_request = None

    def describe(self, _artifact):
        return ArtifactRepresentationDescriptor(
            representation_type=DATAFRAME_REPRESENTATION_TYPE,
            version=1,
            operations=(
                ArtifactRepresentationOperation(name="page"),
                ArtifactRepresentationOperation(
                    name="export.csv",
                    result_kind="stream",
                    media_type="text/csv",
                ),
            ),
        )

    def execute(self, artifact, request, _context):
        if request.operation == "export.csv":
            self.export_request = request.parameters
            return ArtifactRepresentationStream(
                chunks=iter(("id,amount\n", "2,40\n")),
                media_type="text/csv",
                file_name="orders.csv",
                metadata={"row-count": "1", "source-truncated": "false"},
            )
        self.page_request = DataFramePageRequest.model_validate(request.parameters)
        page = DataFramePage(
            fields=[
                DataFrameField(key="field_0", name="id", values=["2"]),
                DataFrameField(key="field_1", name="amount", values=["40"]),
            ],
            page=self.page_request.page,
            page_size=self.page_request.page_size,
            row_count=1,
            has_next_page=False,
            latency_ms=0,
        )
        return ArtifactRepresentationResult(
            representation_type=DATAFRAME_REPRESENTATION_TYPE,
            representation_version=1,
            operation="page",
            payload=page.model_dump(mode="json"),
            consistency="durable_snapshot",
            original_observed_at="2026-08-23T08:00:00Z",
            read_at="2026-08-23T08:01:00Z",
            read_id="read-api",
            source_version=str(artifact.resource_refs[0].version),
            source_fingerprint=str(artifact.payload["queryFingerprint"]),
            notices=("durable",),
        )


def _dataframe_snapshot(provider) -> RuntimeContributionSnapshot:
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
                validator=SnapshotBackedResultViewArtifactPayload,
                owner_id="dbfox.data",
            ),
        ),
        operations=(),
        artifact_representations=(
            ArtifactRepresentationContribution(
                artifact_type="dbfox.data.result_view",
                representation_type=DATAFRAME_REPRESENTATION_TYPE,
                provider=provider,
                owner_id="dbfox.data",
            ),
        ),
    )


def test_artifact_read_and_stream_dispatch_to_capability_representation(
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
            "queryFingerprint": _query_fingerprint(
                "SELECT id, amount FROM orders"
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

    provider = _CapturedDataFrameRepresentation()
    previous = active_runtime_snapshot()
    set_active_runtime_snapshot(_dataframe_snapshot(provider))
    try:
        descriptors = result_module.api_artifact_representations(result_id, db_session)
        page = result_module.api_artifact_representation_read(
            result_id,
            DATAFRAME_REPRESENTATION_TYPE,
            ArtifactRepresentationRequest(
                operation="page",
                parameters={
                    "page": 1,
                    "page_size": 50,
                    "filters": [
                        {"field": "amount", "operator": "gte", "value": 25}
                    ],
                    "sort": [{"field": "amount", "direction": "desc"}],
                },
            ),
            db_session,
        )
        exported = result_module.api_artifact_representation_stream(
            result_id,
            DATAFRAME_REPRESENTATION_TYPE,
            ArtifactRepresentationRequest(
                operation="export.csv",
                parameters={"search": "40"},
            ),
            db_session,
        )
        body = asyncio.run(_streaming_response_text(exported))
    finally:
        set_active_runtime_snapshot(previous)

    assert descriptors[0].representation_type == DATAFRAME_REPRESENTATION_TYPE
    assert page.consistency == "durable_snapshot"
    assert page.payload["fields"][1]["values"] == ["40"]
    assert page.source_version == "1"
    assert page.source_fingerprint == _query_fingerprint(
        "SELECT id, amount FROM orders"
    )
    assert provider.page_request.filters[0].field == "amount"
    assert provider.page_request.sort[0].direction == "desc"
    assert provider.export_request["search"] == "40"
    assert body == "id,amount\n2,40\n"
    assert exported.headers["x-dbfox-representation-row-count"] == "1"


@pytest.mark.parametrize(
    ("page", "page_size"),
    [
        (0, 20),
        (-1, 20),
        (1, 0),
        (1, 501),
    ],
)
def test_dataframe_page_request_rejects_invalid_pagination_bounds(page, page_size):
    with pytest.raises(ValidationError):
        DataFramePageRequest(
            page=page,
            page_size=page_size,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"page": 1, "page_size": 20, "search": "x" * 513},
        {
            "page": 1,
            "page_size": 20,
            "filters": [{"field": "status", "operator": "equals", "value": "paid"}]
            * 17,
        },
        {
            "page": 1,
            "page_size": 20,
            "filters": [
                {"field": "status", "operator": "equals", "value": "x" * 16_385}
            ],
        },
        {
            "page": 1,
            "page_size": 20,
            "filters": [{"field": "status", "operator": "unknown", "value": "paid"}],
        },
    ],
)
def test_dataframe_page_request_rejects_unbounded_query_inputs(payload):
    with pytest.raises(ValidationError):
        DataFramePageRequest.model_validate(payload)


async def _streaming_response_text(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
    return "".join(chunks)
