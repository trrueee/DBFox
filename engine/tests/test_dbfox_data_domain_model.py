"""Conformance for ConnectionProfile -> DatabaseResource separation."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.snapshot import CompletionConstraintContribution
from engine.dlc.api import (
    ArtifactTableExportRequest,
    ArtifactTablePageRequest,
    ArtifactViewFilter,
    ArtifactViewSort,
    DlcOperationContext,
    ResourceScopeRef,
)
from engine.agent.artifact import Artifact, ArtifactRelation, ArtifactRelationType
from engine.models import CredentialLeaseRecord
from engine.runtime_composition import (
    build_attempt_resource_resolver,
    build_product_tool_registry,
)
from engine.security.credential_lease import CredentialLeaseSaga, CredentialLeaseStatus
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault
from engine.tools.runtime import ToolRunContext
from engine.tools.runtime.admission import ToolAdmissionContext
from scripts.build_dbfox_data_dlc_fixture import SOURCE_ROOT, build_dbfox_data_dlc_fixture


def _invoke(snapshot, name: str, project_id: str, payload: dict):
    contribution = snapshot.get_operation("dbfox.data", name)
    assert contribution is not None
    result = contribution.spec.handler(
        contribution.spec.input_model.model_validate(payload),
        DlcOperationContext(
            dlc_id="dbfox.data",
            operation_name=name,
            project_id=project_id,
        ),
    )
    return contribution.spec.output_model.model_validate(result)


def _snapshot(tmp_path: Path):
    built = build_dbfox_data_dlc_fixture(tmp_path / "archives")
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    service.trust_publisher_from_file(
        built.archive,
        expected_package_digest=built.package_digest,
        expected_publisher_key_id=built.publisher_fingerprint,
    )
    service.install_from_file(built.archive)
    service.set_desired_enabled("dbfox.data", True)
    snapshot = ContributionCompiler(service.storage_root).compile(
        built_ins=BuiltinContributionSet()
    )
    assert snapshot.activation_failures == ()
    return service, snapshot


def test_data_source_uses_only_public_extension_api() -> None:
    for source in sorted((SOURCE_ROOT / "backend").rglob("*.py")):
        value = source.read_text(encoding="utf-8")
        assert "from engine" not in value
        assert "import engine" not in value


def test_data_package_declares_the_hosted_resource_connector(tmp_path: Path) -> None:
    _service, snapshot = _snapshot(tmp_path)
    active = next(item for item in snapshot.active_dlcs if item.dlc_id == "dbfox.data")
    assert active.frontend_entrypoint == "frontend/index.js"
    assert (SOURCE_ROOT / "frontend" / "index.js").is_file()
    assert (SOURCE_ROOT / "frontend" / "index.css").is_file()


def test_data_package_owns_query_result_completion_semantics(tmp_path: Path) -> None:
    _service, snapshot = _snapshot(tmp_path)
    assert [
        (item.owner_id, item.constraint.id)
        for item in snapshot.completion_constraints
    ] == [("dbfox.data", "dbfox.data.result_citation")]
    assert [
        (item.owner_id, item.support.id)
        for item in snapshot.completion_supports
    ] == [("dbfox.data", "dbfox.data.query_result")]


def test_data_package_owns_namespaced_artifact_payload_contracts(tmp_path: Path) -> None:
    _service, snapshot = _snapshot(tmp_path)
    assert [
        (item.owner_id, item.artifact_type, item.schema_version)
        for item in snapshot.artifact_contracts
    ] == [
        ("dbfox.data", "dbfox.data.sql", 1),
        ("dbfox.data", "dbfox.data.safety", 1),
        ("dbfox.data", "dbfox.data.result_view", 1),
        ("dbfox.data", "dbfox.data.chart", 1),
    ]
    table_view = snapshot.get_artifact_table_view("dbfox.data.result_view")
    assert table_view is not None
    assert table_view.owner_id == "dbfox.data"
    chart_view = snapshot.get_artifact_chart_view("dbfox.data.chart")
    assert chart_view is not None
    assert chart_view.owner_id == "dbfox.data"


def test_data_sql_validate_uses_authorized_database_handle_and_emits_fenced_artifacts(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "billing.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, total INTEGER)")
        connection.commit()
    finally:
        connection.close()

    _service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "Billing SQLite",
            "provider": "sqlite",
            "initial_database_name": str(database_path),
            "initial_database_display_name": "Billing",
        },
    )
    database = created.databases[0]
    descriptor = snapshot.resource_providers[0](None, "project-a")[0]
    ref = descriptor.to_scope_ref()
    resolved = build_attempt_resource_resolver(snapshot=snapshot).resolve((ref,))
    context = ToolRunContext.for_invocation(
        request=None,
        idempotency_key="validate-sqlite",
        scope_refs=(ref,),
        resources=resolved,
    )
    registry = build_product_tool_registry(snapshot)
    assert registry.owner_of("sql_validate") == "dbfox.data"
    tool = registry.require("sql_validate")

    outcome = tool.run(
        tool.input_model.model_validate(
            {"database_id": database.id, "sql": "SELECT id, total FROM orders"}
        ),
        context,
    )
    assert outcome.output.can_execute is True
    assert any(
        "EXPLAIN dry-run validated" in message
        for message in outcome.output.messages
    )
    assert [draft.type for draft in outcome.artifacts] == [
        "dbfox.data.safety",
        "dbfox.data.sql",
    ]
    assert all(draft.resource_refs == (ref,) for draft in outcome.artifacts)
    assert outcome.artifacts[1].relations[0].draft_key == "safety"
    assert outcome.artifacts[1].payload["queryFingerprint"].startswith("query_")

    rejected = tool.run(
        tool.input_model.model_validate(
            {"database_id": database.id, "sql": "SELECT id FROM missing_orders"}
        ),
        context,
    )
    assert rejected.output.can_execute is False
    assert "schema_error" in rejected.output.blocked_reasons


def test_data_sql_execute_rechecks_artifacts_and_reads_sqlite_in_dlc(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "execute.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, total INTEGER)")
        connection.executemany(
            "INSERT INTO orders (id, total) VALUES (?, ?)",
            [(1, 25), (2, 40)],
        )
        connection.commit()
    finally:
        connection.close()

    _service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "Executable SQLite",
            "provider": "sqlite",
            "environment": "dev",
            "initial_database_name": str(database_path),
        },
    )
    database = created.databases[0]
    ref = snapshot.resource_providers[0](None, "project-a")[0].to_scope_ref()
    resolved = build_attempt_resource_resolver(snapshot=snapshot).resolve((ref,))
    registry = build_product_tool_registry(snapshot)
    validate_tool = registry.require("sql_validate")
    validation = validate_tool.run(
        validate_tool.input_model.model_validate(
            {
                "database_id": database.id,
                "sql": "SELECT id, total FROM orders ORDER BY id",
            }
        ),
        ToolRunContext.for_invocation(
            request=None,
            tool_name="sql_validate",
            idempotency_key="validate-before-execute",
            scope_refs=(ref,),
            resources=resolved,
        ),
    )
    safety_draft, sql_draft = validation.artifacts
    safety = Artifact(
        id="artifact-safety",
        session_id="session-data",
        run_id="run-data",
        type=safety_draft.type,
        title=safety_draft.title,
        payload=safety_draft.payload,
        resource_refs=safety_draft.resource_refs,
    )
    sql_artifact = Artifact(
        id="artifact-sql",
        session_id="session-data",
        run_id="run-data",
        type=sql_draft.type,
        title=sql_draft.title,
        payload=sql_draft.payload,
        resource_refs=sql_draft.resource_refs,
        relations=[
            ArtifactRelation(
                relation=ArtifactRelationType.VALIDATED_BY,
                artifact_id=safety.id,
            )
        ],
    )
    artifacts = {safety.id: safety, sql_artifact.id: sql_artifact}
    execute_tool = registry.require("sql_execute_readonly")
    execute_input = execute_tool.input_model.model_validate(
        {
            "database_id": database.id,
            "validation_artifact_id": sql_artifact.id,
        }
    )
    admission = execute_tool.admit(
        execute_input,
        ToolAdmissionContext(
            session_id="session-data",
            run_id="run-data",
            resource_refs=(ref,),
            artifact_loader=artifacts.get,
            artifact_relation_loader=lambda _id, _relation: (),
        ),
    )
    assert admission.status == "allowed"

    outcome = execute_tool.run(
        execute_input,
        ToolRunContext.for_invocation(
            request=None,
            tool_name="sql_execute_readonly",
            invocation_id="invocation-execute-sqlite",
            idempotency_key="execute-sqlite",
            scope_refs=(ref,),
            resources=resolved,
            artifact_loader=artifacts.get,
            artifact_relation_loader=lambda _id, _relation: (),
        ),
    )
    assert outcome.output.rows == [
        {"id": "1", "total": "25"},
        {"id": "2", "total": "40"},
    ]
    assert outcome.output.returned_rows == 2
    assert outcome.artifacts[0].type == "dbfox.data.result_view"
    assert outcome.artifacts[0].payload_ref is not None
    assert outcome.artifacts[0].relations[0].artifact_id == sql_artifact.id

    result_draft = outcome.artifacts[0]
    result_artifact = Artifact(
        id="artifact-query-result",
        session_id="session-data",
        run_id="run-data",
        type=result_draft.type,
        title=result_draft.title,
        payload=result_draft.payload,
        payload_ref=result_draft.payload_ref,
        resource_refs=result_draft.resource_refs,
    )

    table_view = snapshot.get_artifact_table_view(result_artifact.type)
    assert table_view is not None
    page = table_view.provider.page(
        result_artifact,
        ArtifactTablePageRequest(
            page=1,
            page_size=1,
            filters=(
                ArtifactViewFilter(column="total", operator="gte", value=25),
            ),
            sort=(ArtifactViewSort(column="total", direction="desc"),),
            search="",
            count_mode="exact",
        ),
    )
    assert page.consistency == "durable_snapshot"
    assert page.rows == [{"id": "2", "total": "40"}]
    assert page.row_count == 2
    assert page.has_next_page is True
    assert "without SQL reexecution" in page.notices[0]
    exported = table_view.provider.export_csv(
        result_artifact,
        ArtifactTableExportRequest(
            filters=(
                ArtifactViewFilter(column="total", operator="gt", value=25),
            ),
        ),
    )
    assert exported.row_count == 1
    assert "".join(exported.chunks) == "id,total\n2,40\n"

    def result_context(tool_name: str) -> ToolRunContext:
        return ToolRunContext.for_invocation(
            request=None,
            tool_name=tool_name,
            invocation_id=f"invocation-{tool_name}",
            idempotency_key=f"invoke-{tool_name}",
            scope_refs=(ref,),
            resources=resolved,
            artifact_loader=lambda artifact_id: (
                result_artifact if artifact_id == result_artifact.id else None
            ),
        )

    profile_tool = registry.require("result_profile")
    profiled = profile_tool.run(
        profile_tool.input_model.model_validate(
            {
                "result_artifact_id": result_artifact.id,
                "columns": ["total"],
                "sample_size": 20,
            }
        ),
        result_context("result_profile"),
    )
    assert profiled.profiles[0]["kind"] == "number"
    assert profiled.profiles[0]["numeric"]["mean"] == 32.5

    chart_tool = registry.require("chart_create")
    charted = chart_tool.run(
        chart_tool.input_model.model_validate(
            {
                "result_artifact_id": result_artifact.id,
                "x": "id",
                "y": "total",
            }
        ),
        result_context("chart_create"),
    )
    assert charted.output.chartable is True
    assert charted.output.chart_type == "scatter"
    assert charted.artifacts[0].type == "dbfox.data.chart"
    assert charted.artifacts[0].resource_refs == (ref,)
    assert charted.artifacts[0].relations[0].artifact_id == result_artifact.id
    chart_view = snapshot.get_artifact_chart_view(charted.artifacts[0].type)
    assert chart_view is not None
    chart_artifact = Artifact(
        id="artifact-chart-result",
        session_id="session-data",
        run_id="run-data",
        type=charted.artifacts[0].type,
        title=charted.artifacts[0].title,
        payload=charted.artifacts[0].payload,
        resource_refs=charted.artifacts[0].resource_refs,
        relations=[
            ArtifactRelation(
                relation=ArtifactRelationType.DERIVED_FROM,
                artifact_id=result_artifact.id,
            )
        ],
    )
    chart_data = chart_view.provider.data(chart_artifact, result_artifact)
    assert chart_data.consistency == "durable_snapshot"
    assert chart_data.series == [
        {"label": "1", "value": 25.0},
        {"label": "2", "value": 40.0},
    ]


def test_data_sql_validate_requires_database_id_for_multi_database_authority(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / "one.sqlite3", tmp_path / "two.sqlite3"]
    for path in paths:
        connection = sqlite3.connect(path)
        connection.close()

    _service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "SQLite files",
            "provider": "sqlite",
            "initial_database_name": str(paths[0]),
            "initial_database_display_name": "One",
        },
    )
    second = _invoke(
        snapshot,
        "databases.add",
        "project-a",
        {
            "profile_id": created.profile.id,
            "database_name": str(paths[1]),
            "display_name": "Two",
        },
    )
    refs = tuple(
        descriptor.to_scope_ref()
        for descriptor in snapshot.resource_providers[0](None, "project-a")
    )
    resolved = build_attempt_resource_resolver(snapshot=snapshot).resolve(refs)
    context = ToolRunContext.for_invocation(
        request=None,
        idempotency_key="validate-two-sqlite",
        scope_refs=refs,
        resources=resolved,
    )
    tool = build_product_tool_registry(snapshot).require("sql_validate")

    with pytest.raises(Exception, match="database_id is required"):
        tool.run(
            tool.input_model.model_validate({"sql": "SELECT 1"}),
            context,
        )
    selected = tool.run(
        tool.input_model.model_validate(
            {"database_id": second.id, "sql": "SELECT 1"}
        ),
        context,
    )
    assert selected.output.can_execute is True
    assert selected.artifacts[0].resource_refs[0].id == second.id


def test_data_catalog_refresh_browse_search_and_inspect_are_database_scoped(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "catalog-one.sqlite3"
    second_path = tmp_path / "catalog-two.sqlite3"
    first_connection = sqlite3.connect(first_path)
    try:
        first_connection.executescript(
            """
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL
            );
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                total INTEGER
            );
            CREATE INDEX ix_orders_customer ON orders(customer_id);
            INSERT INTO customers (id, email) VALUES
                (1, 'alice@example.com'),
                (2, 'bob@example.com');
            INSERT INTO orders (id, customer_id, total) VALUES
                (10, 1, 25),
                (11, 2, 40);
            """
        )
        first_connection.commit()
    finally:
        first_connection.close()
    second_connection = sqlite3.connect(second_path)
    try:
        second_connection.execute("CREATE TABLE private_notes (id INTEGER PRIMARY KEY)")
        second_connection.commit()
    finally:
        second_connection.close()

    _service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "Catalog SQLite files",
            "provider": "sqlite",
            "initial_database_name": str(first_path),
            "initial_database_display_name": "Commerce",
        },
    )
    first = created.databases[0]
    second = _invoke(
        snapshot,
        "databases.add",
        "project-a",
        {
            "profile_id": created.profile.id,
            "database_name": str(second_path),
            "display_name": "Private",
        },
    )
    refs = tuple(
        descriptor.to_scope_ref()
        for descriptor in snapshot.resource_providers[0](None, "project-a")
    )
    resolved = build_attempt_resource_resolver(snapshot=snapshot).resolve(refs)
    registry = build_product_tool_registry(snapshot)
    assert {
        name: registry.owner_of(name)
        for name in (
            "catalog_overview",
            "catalog_refresh",
            "schema_list",
            "schema_search",
            "schema_inspect",
            "result_inspect",
        )
    } == {
        "catalog_overview": "dbfox.data",
        "catalog_refresh": "dbfox.data",
        "schema_list": "dbfox.data",
        "schema_search": "dbfox.data",
        "schema_inspect": "dbfox.data",
        "result_inspect": "dbfox.data",
    }

    def context(tool_name: str, invocation_id: str) -> ToolRunContext:
        return ToolRunContext.for_invocation(
            request=None,
            tool_name=tool_name,
            invocation_id=invocation_id,
            idempotency_key=invocation_id,
            scope_refs=refs,
            resources=resolved,
        )

    overview_tool = registry.require("catalog_overview")
    before = overview_tool.run(
        overview_tool.input_model.model_validate({"database_id": first.id}),
        context("catalog_overview", "catalog-overview-before"),
    )
    assert before.catalog_status == "uninitialized"
    assert before.table_count == 0

    refresh_tool = registry.require("catalog_refresh")
    refreshed = refresh_tool.run(
        refresh_tool.input_model.model_validate({"database_id": first.id}),
        context("catalog_refresh", "catalog-refresh-first"),
    )
    assert refreshed.status == "ready"
    assert refreshed.table_count == 2
    assert refreshed.catalog_revision == 1

    list_tool = registry.require("schema_list")
    listed = list_tool.run(
        list_tool.input_model.model_validate(
            {"database_id": first.id, "limit": 1}
        ),
        context("schema_list", "catalog-list-first"),
    )
    assert [table.table_name for table in listed.tables] == ["customers"]
    assert listed.has_more is True
    assert listed.next_cursor is not None
    next_page = list_tool.run(
        list_tool.input_model.model_validate(
            {
                "database_id": first.id,
                "limit": 1,
                "cursor": listed.next_cursor.model_dump(),
            }
        ),
        context("schema_list", "catalog-list-second"),
    )
    assert [table.table_name for table in next_page.tables] == ["orders"]

    search_tool = registry.require("schema_search")
    searched = search_tool.run(
        search_tool.input_model.model_validate(
            {"database_id": first.id, "queries": ["customer"]}
        ),
        context("schema_search", "catalog-search"),
    )
    assert {item["table_name"] for item in searched.candidates} >= {
        "customers",
        "orders",
    }

    inspect_tool = registry.require("schema_inspect")
    inspected = inspect_tool.run(
        inspect_tool.input_model.model_validate(
            {"database_id": first.id, "targets": ["orders"]}
        ),
        context("schema_inspect", "catalog-inspect"),
    )
    details = inspected.inspections[0].details
    assert details.name == "orders"
    assert details.primary_key == ["id"]
    assert details.foreign_keys_out[0].references.table == "customers"
    assert details.indexes[0].name == "ix_orders_customer"

    preview_tool = registry.require("data_preview")
    previewed = preview_tool.run(
        preview_tool.input_model.model_validate(
            {
                "database_id": first.id,
                "table": "customers",
                "columns": ["id", "email"],
                "where": {"column": "id", "op": ">=", "value": 1},
                "order_by": [{"column": "id", "direction": "DESC"}],
                "limit": 2,
            }
        ),
        context("data_preview", "data-preview"),
    )
    assert previewed.output.rows == [
        {"id": "2", "email": "[REDACTED]"},
        {"id": "1", "email": "[REDACTED]"},
    ]
    assert previewed.output.parameters == {"dbfox_p0": 1}
    assert previewed.output.column_summaries[1]["sensitive"] is True
    assert [draft.type for draft in previewed.artifacts] == [
        "dbfox.data.sql",
        "dbfox.data.result_view",
    ]
    first_ref = next(ref for ref in refs if ref.id == first.id)
    assert all(draft.resource_refs == (first_ref,) for draft in previewed.artifacts)
    assert previewed.artifacts[1].payload_ref is not None

    from engine.agent.artifact import Artifact

    result_draft = previewed.artifacts[1]
    result_artifact = Artifact(
        id="artifact-result-preview",
        session_id="session-preview",
        run_id="run-preview",
        type=result_draft.type,
        title=result_draft.title,
        payload={
            **result_draft.payload,
            "sourceSqlArtifactId": "artifact-sql-preview",
        },
        payload_ref=result_draft.payload_ref,
        resource_refs=result_draft.resource_refs,
    )
    inspect_result_tool = registry.require("result_inspect")

    def result_context(artifact: Artifact, invocation_id: str) -> ToolRunContext:
        return ToolRunContext.for_invocation(
            request=None,
            tool_name="result_inspect",
            invocation_id=invocation_id,
            idempotency_key=invocation_id,
            scope_refs=refs,
            resources=resolved,
            artifact_loader=lambda artifact_id: (
                artifact if artifact_id == artifact.id else None
            ),
        )

    # Result inspection is a snapshot read: changing the source cannot alter pages.
    changed_source = sqlite3.connect(first_path)
    try:
        changed_source.execute("DELETE FROM customers")
        changed_source.commit()
    finally:
        changed_source.close()
    first_page = inspect_result_tool.run(
        inspect_result_tool.input_model.model_validate(
            {"result_artifact_id": result_artifact.id, "page_size": 1}
        ),
        result_context(result_artifact, "result-inspect-page-one"),
    )
    second_page = inspect_result_tool.run(
        inspect_result_tool.input_model.model_validate(
            {
                "result_artifact_id": result_artifact.id,
                "page": 2,
                "page_size": 1,
            }
        ),
        result_context(result_artifact, "result-inspect-page-two"),
    )
    assert first_page.rows == [{"id": "2", "email": "[REDACTED]"}]
    assert second_page.rows == [{"id": "1", "email": "[REDACTED]"}]
    assert first_page.row_count == 2
    assert first_page.has_next_page is True
    assert second_page.has_next_page is False
    assert "without SQL reexecution" in first_page.notices[0]

    second_ref = next(ref for ref in refs if ref.id == second.id)
    forged = result_artifact.model_copy(
        update={"id": "artifact-forged-database", "resource_refs": (second_ref,)}
    )
    with pytest.raises(Exception, match="does not match its durable payload"):
        inspect_result_tool.run(
            inspect_result_tool.input_model.model_validate(
                {"result_artifact_id": forged.id}
            ),
            result_context(forged, "result-inspect-forged"),
        )
    differently_filtered = preview_tool.run(
        preview_tool.input_model.model_validate(
            {
                "database_id": first.id,
                "table": "customers",
                "columns": ["id"],
                "where": {"column": "id", "op": ">=", "value": 2},
            }
        ),
        context("data_preview", "data-preview-filter-identity"),
    )
    assert (
        differently_filtered.artifacts[0].payload["queryFingerprint"]
        != previewed.artifacts[0].payload["queryFingerprint"]
    )

    default_preview = preview_tool.run(
        preview_tool.input_model.model_validate(
            {"database_id": first.id, "table": "customers"}
        ),
        context("data_preview", "data-preview-default"),
    )
    assert default_preview.output.columns == ["id"]
    assert all("email" not in row for row in default_preview.output.rows)

    second_overview = overview_tool.run(
        overview_tool.input_model.model_validate({"database_id": second.id}),
        context("catalog_overview", "catalog-overview-second"),
    )
    assert second_overview.catalog_status == "uninitialized"
    assert second_overview.catalog_revision == 0
    with pytest.raises(Exception, match="database_id is required"):
        refresh_tool.run(
            refresh_tool.input_model.model_validate({}),
            context("catalog_refresh", "catalog-refresh-ambiguous"),
        )
    with pytest.raises(Exception, match="database_id is required"):
        preview_tool.run(
            preview_tool.input_model.model_validate({"table": "customers"}),
            context("data_preview", "data-preview-ambiguous"),
        )


def test_sqlite_backup_restore_is_isolated_version_fenced_and_data_owned(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "backup-source.sqlite3"
    connection = sqlite3.connect(source_path)
    try:
        connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, total INTEGER)")
        connection.execute("INSERT INTO orders (id, total) VALUES (1, 25)")
        connection.commit()
    finally:
        connection.close()

    _service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "Backup SQLite",
            "provider": "sqlite",
            "initial_database_name": str(source_path),
        },
    )
    database = created.databases[0]
    initial_ref = snapshot.resource_providers[0](None, "project-a")[0].to_scope_ref()
    backup = _invoke(
        snapshot,
        "backups.create",
        "project-a",
        {"database_id": database.id, "label": "Before mutation"},
    )
    assert backup.status == "success"
    assert backup.backup_type == "sqlite_online_backup"
    assert backup.resource_version == initial_ref.version
    assert backup.file_size_bytes and backup.file_size_bytes > 0
    assert backup.checksum_sha256 and len(backup.checksum_sha256) == 64

    changed = sqlite3.connect(source_path)
    try:
        changed.execute("UPDATE orders SET total = 99 WHERE id = 1")
        changed.commit()
    finally:
        changed.close()
    restored = _invoke(
        snapshot,
        "backups.restore",
        "project-a",
        {
            "backup_id": backup.id,
            "expected_resource_version": str(initial_ref.version),
            "confirmation": "restore-to-isolated-database",
        },
    )
    assert restored.previous_resource_version == initial_ref.version
    assert restored.committed_resource_version != initial_ref.version
    assert restored.validated_table_count == 1
    assert Path(restored.target_database_name) != source_path
    isolated = sqlite3.connect(restored.target_database_name)
    try:
        assert isolated.execute("SELECT total FROM orders WHERE id = 1").fetchone()[0] == 25
    finally:
        isolated.close()
    original = sqlite3.connect(source_path)
    try:
        assert original.execute("SELECT total FROM orders WHERE id = 1").fetchone()[0] == 99
    finally:
        original.close()

    current_ref = snapshot.resource_providers[0](None, "project-a")[0].to_scope_ref()
    assert current_ref.version == restored.committed_resource_version
    listed = _invoke(snapshot, "backups.list", "project-a", {})
    assert [item.id for item in listed.backups] == [backup.id]
    with pytest.raises(Exception, match="version changed"):
        _invoke(
            snapshot,
            "backups.restore",
            "project-a",
            {
                "backup_id": backup.id,
                "expected_resource_version": str(initial_ref.version),
                "confirmation": "restore-to-isolated-database",
            },
        )


def test_network_backup_fails_closed_without_pinned_official_client(
    tmp_path: Path,
) -> None:
    _service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "Network backup",
            "provider": "postgresql",
            "host": "db.internal",
            "username": "analyst",
            "password_credential_ref": "cred_datasource_password_backup",
            "initial_database_name": "billing",
        },
    )
    with pytest.raises(Exception, match="pinned official native client"):
        _invoke(
            snapshot,
            "backups.create",
            "project-a",
            {"database_id": created.databases[0].id},
        )


def test_data_artifact_contracts_remain_snapshot_scoped_after_core_freeze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from engine.agent.artifact import artifact_payload_contracts, validate_artifact_payload
    from engine.runtime_composition import set_active_runtime_snapshot

    monkeypatch.setattr(artifact_payload_contracts, "_frozen", True)
    _service, snapshot = _snapshot(tmp_path)
    set_active_runtime_snapshot(snapshot)
    try:
        assert validate_artifact_payload(
            "dbfox.data.sql",
            {
                "sql": "SELECT 1",
                "safeSql": "SELECT 1",
                "dialect": "sqlite",
                "queryFingerprint": "fingerprint",
                "parameters": {},
            },
            schema_version=1,
        )["safeSql"] == "SELECT 1"
    finally:
        set_active_runtime_snapshot(None)


def test_data_package_owns_credential_reference_recovery_probe(
    tmp_path: Path,
) -> None:
    _service, snapshot = _snapshot(tmp_path)
    credential_ref = "cred_datasource_password_probe"
    _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "Recovery Probe",
            "provider": "mysql",
            "host": "db.internal",
            "username": "analyst",
            "password_credential_ref": credential_ref,
        },
    )

    assert [item.owner_id for item in snapshot.credential_reference_probes] == [
        "dbfox.data"
    ]
    probe = snapshot.credential_reference_probes[0].probe
    assert probe(None, frozenset({credential_ref})) is True
    assert probe(None, frozenset({"cred_datasource_password_other"})) is False
    assert probe(
        None,
        frozenset({credential_ref, "cred_datasource_password_other"}),
    ) is False


def test_data_package_probe_recovers_interrupted_core_credential_claim(
    tmp_path: Path,
    db_session,
) -> None:
    _service, snapshot = _snapshot(tmp_path)
    vault = InMemoryCredentialVault()
    credential_ref = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="durable-secret",
    )
    saga = CredentialLeaseSaga(
        db_session,
        vault,
        reference_probes={
            item.owner_id: item.probe
            for item in snapshot.credential_reference_probes
        },
    )
    lease_id = saga.issue({credential_ref})
    db_session.commit()
    saga.claim(
        lease_id,
        {credential_ref},
        owner_id="dbfox.data",
        owner_operation="profiles.create",
        owner_project_id="project-a",
    )
    db_session.commit()

    _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "Recovered Profile",
            "provider": "mysql",
            "host": "db.internal",
            "username": "analyst",
            "password_credential_ref": credential_ref,
        },
    )
    saga.reconcile()

    lease = db_session.get(CredentialLeaseRecord, lease_id)
    assert lease is not None
    assert lease.status == CredentialLeaseStatus.COMMITTED.value
    assert vault.get(credential_ref) == "durable-secret"


def test_data_completion_conflict_rejects_the_whole_package(tmp_path: Path) -> None:
    built = build_dbfox_data_dlc_fixture(tmp_path / "archives")
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    service.trust_publisher_from_file(
        built.archive,
        expected_package_digest=built.package_digest,
        expected_publisher_key_id=built.publisher_fingerprint,
    )
    service.install_from_file(built.archive)
    service.set_desired_enabled("dbfox.data", True)

    from engine.tools.builtin.data_capability import legacy_data_completion_constraints

    snapshot = ContributionCompiler(service.storage_root).compile(
        built_ins=BuiltinContributionSet(
            identifiers=("legacy.dbfox.data",),
            completion_constraints=tuple(
                CompletionConstraintContribution(
                    constraint=constraint,
                    owner_id="dbfox.data",
                )
                for constraint in legacy_data_completion_constraints()
            ),
        )
    )

    assert snapshot.active_dlcs == ()
    assert snapshot.resource_providers == ()
    assert snapshot.operations == ()
    assert [item.owner_id for item in snapshot.completion_constraints] == [
        "dbfox.data"
    ]
    assert len(snapshot.activation_failures) == 1
    assert snapshot.activation_failures[0].error_code == "registration_conflict"


def test_one_profile_owns_multiple_database_resources_and_only_databases_are_authority(
    tmp_path: Path,
) -> None:
    _service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "Production MySQL",
            "provider": "mysql",
            "host": "db.internal",
            "port": 3306,
            "username": "analyst",
            "password_credential_ref": "credential:mysql-production",
            "is_read_only": True,
            "environment": "prod",
            "initial_database_name": "billing",
            "initial_database_display_name": "Billing",
        },
    )
    profile = created.profile
    billing = created.databases[0]
    analytics = _invoke(
        snapshot,
        "databases.add",
        "project-a",
        {
            "profile_id": profile.id,
            "database_name": "analytics",
            "display_name": "Analytics",
        },
    )

    groups = _invoke(snapshot, "profiles.list", "project-a", {})
    assert len(groups.profiles) == 1
    assert groups.profiles[0].profile.id == profile.id
    assert {item.database_name for item in groups.profiles[0].databases} == {
        "billing",
        "analytics",
    }

    descriptors = snapshot.resource_providers[0](None, "project-a")
    assert {(item.kind, item.id, item.version) for item in descriptors} == {
        ("dbfox.data.database", billing.id, "1:1"),
        ("dbfox.data.database", analytics.id, "1:1"),
    }
    assert profile.id not in {item.id for item in descriptors}

    refs = tuple(item.to_scope_ref() for item in descriptors)
    resolved = build_attempt_resource_resolver(snapshot=snapshot).resolve(refs)
    context = ToolRunContext.for_invocation(
        request=None,
        idempotency_key="two-databases",
        scope_refs=refs,
        resources=resolved,
    )
    assert {
        handle.database.database_name
        for handle in context.resources("dbfox.data.database")
    } == {"billing", "analytics"}
    with pytest.raises(RuntimeError, match="exactly one"):
        context.require_one("dbfox.data.database")

    resolver = snapshot.resource_resolvers[0]
    handle = resolver.resolver(
        ResourceScopeRef(
            kind="dbfox.data.database",
            id=analytics.id,
            version="1:1",
        )
    )
    assert handle.profile.id == profile.id
    assert handle.database.database_name == "analytics"
    assert handle.profile.password_credential_ref == "credential:mysql-production"


def test_profile_generation_fences_every_child_database_without_rewriting_children(
    tmp_path: Path,
) -> None:
    _service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "Postgres",
            "provider": "postgresql",
            "host": "old.internal",
            "port": 5432,
            "username": "analyst",
            "password_credential_ref": "cred_datasource_password_postgres",
            "initial_database_name": "app",
        },
    )
    database = created.databases[0]
    old_ref = ResourceScopeRef(
        kind="dbfox.data.database",
        id=database.id,
        version="1:1",
    )
    resolver = snapshot.resource_resolvers[0].resolver
    assert resolver(old_ref).profile.host == "old.internal"

    updated = _invoke(
        snapshot,
        "profiles.update",
        "project-a",
        {
            "profile_id": created.profile.id,
            "expected_generation": 1,
            "name": "Postgres",
            "host": "new.internal",
            "port": 5432,
            "username": "analyst",
            "password_credential_ref": "cred_datasource_password_postgres",
            "is_read_only": False,
            "environment": "prod",
        },
    )
    assert updated.profile.connection_generation == 2
    assert updated.databases[0].resource_generation == 1
    with pytest.raises(ValueError, match="version"):
        resolver(old_ref)
    current = resolver(
        ResourceScopeRef(
            kind="dbfox.data.database",
            id=database.id,
            version="2:1",
        )
    )
    assert current.profile.host == "new.internal"


def test_project_boundary_and_cascade_are_enforced_in_dlc_state(tmp_path: Path) -> None:
    service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "SQLite",
            "provider": "sqlite",
            "initial_database_name": "C:/data/local.db",
            "initial_database_display_name": "local.db",
        },
    )
    with pytest.raises(Exception):
        _invoke(
            snapshot,
            "databases.add",
            "project-b",
            {
                "profile_id": created.profile.id,
                "database_name": "foreign",
            },
        )
    deleted = _invoke(
        snapshot,
        "profiles.delete",
        "project-a",
        {"profile_id": created.profile.id},
    )
    assert deleted.deleted is True
    assert snapshot.resource_providers[0](None, "project-a") == ()
    state_path = service.storage_root / "data" / "dbfox.data" / "state.sqlite3"
    assert state_path.is_file()


def test_profile_validation_rejects_incomplete_or_mixed_connection_modes(
    tmp_path: Path,
) -> None:
    _service, snapshot = _snapshot(tmp_path)
    with pytest.raises(Exception, match="username"):
        _invoke(
            snapshot,
            "profiles.create",
            "project-a",
            {
                "name": "Incomplete MySQL",
                "provider": "mysql",
                "host": "db.internal",
                "password_credential_ref": "cred_datasource_password_incomplete",
            },
        )
    with pytest.raises(Exception, match="SQLite"):
        _invoke(
            snapshot,
            "profiles.create",
            "project-a",
            {
                "name": "Invalid SQLite",
                "provider": "sqlite",
                "host": "localhost",
                "initial_database_name": "C:/data/local.db",
            },
        )
    with pytest.raises(Exception, match="SSH"):
        _invoke(
            snapshot,
            "profiles.create",
            "project-a",
            {
                "name": "Invalid SSH",
                "provider": "postgresql",
                "host": "db.internal",
                "username": "analyst",
                "password_credential_ref": "cred_datasource_password_ssh",
                "ssh_enabled": True,
            },
        )


def test_database_identity_change_has_its_own_generation_fence(tmp_path: Path) -> None:
    _service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "SQLite",
            "provider": "sqlite",
            "initial_database_name": "C:/data/old.db",
            "initial_database_display_name": "Old",
        },
    )
    database = created.databases[0]
    resolver = snapshot.resource_resolvers[0].resolver
    old_ref = ResourceScopeRef(
        kind="dbfox.data.database",
        id=database.id,
        version="1:1",
    )
    assert resolver(old_ref).database.database_name.endswith("old.db")

    updated = _invoke(
        snapshot,
        "databases.update",
        "project-a",
        {
            "database_id": database.id,
            "expected_generation": 1,
            "database_name": "C:/data/new.db",
            "display_name": "New",
        },
    )
    assert updated.resource_generation == 2
    with pytest.raises(ValueError, match="version"):
        resolver(old_ref)
    current = resolver(
        ResourceScopeRef(
            kind="dbfox.data.database",
            id=database.id,
            version="1:2",
        )
    )
    assert current.database.database_name.endswith("new.db")


def test_disabling_data_removes_capabilities_without_deleting_domain_state(
    tmp_path: Path,
) -> None:
    service, snapshot = _snapshot(tmp_path)
    created = _invoke(
        snapshot,
        "profiles.create",
        "project-a",
        {
            "name": "Local SQLite",
            "provider": "sqlite",
            "initial_database_name": str(tmp_path / "local.db"),
            "initial_database_display_name": "Local",
        },
    )

    service.set_desired_enabled("dbfox.data", False)
    disabled = ContributionCompiler(service.storage_root).compile(
        built_ins=BuiltinContributionSet()
    )
    assert disabled.active_dlcs == ()
    assert disabled.resource_providers == ()
    assert disabled.operations == ()
    assert disabled.completion_constraints == ()
    assert disabled.completion_supports == ()
    assert disabled.credential_reference_probes == ()

    service.set_desired_enabled("dbfox.data", True)
    restored = ContributionCompiler(service.storage_root).compile(
        built_ins=BuiltinContributionSet()
    )
    groups = _invoke(restored, "profiles.list", "project-a", {})
    assert groups.profiles[0].profile.id == created.profile.id
    assert groups.profiles[0].databases[0].id == created.databases[0].id
