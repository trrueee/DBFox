from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from engine.errors import GuardrailValidationError, ToolInputError
from engine.tools.builtin.catalog import (
    CatalogRefreshTool,
    SchemaInspectTool,
    SchemaListTool,
    SchemaSearchTool,
)
from engine.runtime_composition import build_product_tool_registry
from dlcs.dbfox_data.backend.tool_contracts import (
    ChartCreateInput,
    DatabaseTargetInput,
    ResultProfileInput,
    SchemaListInput,
    SchemaSearchInput,
)
from dlcs.dbfox_data.backend.result_analysis import (
    infer_chart_type,
    profile_rows,
    resolve_chart_suggestion,
)
from engine.tools.db.inspect import db_inspect
from engine.tools.db.observe import _build_observation_context, db_observe
from engine.tools.db.preview import db_preview
from engine.tools.db.search import MAX_SEARCH_TOKENS, _tokenize_search_query, db_search
from engine.tools.db.sql_execution import sql_execute_readonly, sql_validate
from engine.tools.runtime import ToolRunContext, ToolRuntime
from engine.models import DomainTagRule, QueryHistory, SchemaSearchDoc, SchemaTable
from engine.environment.schema_catalog_sync import ensure_catalog
from engine.json_codec import byte_size
from engine.resource import ResourceScopeRef


def sync_schema(db_session, datasource_id: str):
    result = ensure_catalog(db_session, datasource_id)
    db_session.commit()
    return result


def _ensure_default_rules(db_session, datasource_id: str) -> None:
    default_patterns = [
        ("user", ["user", "member", "customer", "account"]),
        ("order", ["order", "cart", "coupon"]),
        ("product", ["product", "category", "sku", "inventory", "item"]),
        ("payment", ["payment", "pay", "refund", "transaction"]),
        ("shipping", ["shipping", "address", "carrier", "logistics"]),
        ("analytics", ["analytics", "click", "recommendation", "event", "log"]),
        ("system", ["system", "admin", "setting", "config"]),
        ("content", ["article", "post", "comment", "review", "tag"]),
    ]
    for tag, needles in default_patterns:
        for needle in needles:
            db_session.add(
                DomainTagRule(
                    data_source_id=datasource_id, pattern=needle, tag=tag, priority=10
                )
            )
    db_session.commit()


def test_db_observe_returns_catalog_map(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    _ensure_default_rules(db_session, test_datasource.id)
    result = db_observe(db_session, test_datasource.id)
    assert result["dialect"] == "sqlite"
    assert result["table_count"] >= 20
    schemas = result["schemas"]
    assert schemas[0]["name"] == "main"
    users = next(t for t in schemas[0]["tables"] if t["name"] == "users")
    assert users["columns"] >= 5
    assert "user" in users["tags"]
    assert any(domain["label"] == "user" for domain in result["domains"])


def test_db_observe_tables_mode_includes_connected_tables(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_observe(db_session, test_datasource.id)
    orders = next(t for t in result["schemas"][0]["tables"] if t["name"] == "orders")
    assert "users" in orders["connected_tables"]
    assert orders["primary_key"] == ["id"]


def test_db_observe_catalog_context_is_per_call_and_immutable(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)
    tables = list(test_datasource.tables)

    first = _build_observation_context(db_session, test_datasource.id, tables)
    second = _build_observation_context(db_session, test_datasource.id, tables)

    assert first is not second
    assert first.table_names == second.table_names
    with pytest.raises(TypeError):
        first.table_names["unexpected"] = "other"  # type: ignore[index]


def test_db_observe_large_catalog_does_not_load_column_graph(
    db_session,
    test_datasource,
) -> None:
    sync_schema(db_session, test_datasource.id)
    datasource_id = str(test_datasource.id)
    existing = (
        db_session.query(SchemaTable)
        .filter(SchemaTable.data_source_id == datasource_id)
        .count()
    )
    for index in range(max(0, 31 - existing)):
        db_session.add(
            SchemaTable(
                data_source_id=datasource_id,
                table_schema="main",
                table_name=f"large_catalog_{index:02d}",
                table_type="table",
            )
        )
    db_session.commit()
    statements: list[str] = []

    def capture_select(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", capture_select)
    try:
        result = db_observe(db_session, datasource_id)
    finally:
        event.remove(bind, "before_cursor_execute", capture_select)

    assert result["mode"] == "summary"
    assert result["table_count"] >= 31
    assert all("tables" not in schema for schema in result["schemas"])
    assert not any("schema_columns" in statement.lower() for statement in statements)


def test_schema_list_queries_only_requested_cursor_page(
    db_session,
    test_datasource,
) -> None:
    sync_schema(db_session, test_datasource.id)
    datasource_id = str(test_datasource.id)
    statements: list[str] = []

    def capture_select(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", capture_select)
    try:
        result = SchemaListTool().run(
            SchemaListInput(limit=5),
            ToolRunContext.for_invocation(
                request=SimpleNamespace(
                    datasource_id=datasource_id,
                    session_id="session_test",
                ),
                idempotency_key="schema-list-test",
                resources={("dbfox.data.database", str(datasource_id)): db_session},
                scope_refs=(ResourceScopeRef(kind="dbfox.data.database", id=datasource_id, version=1),),
                metadata_session=db_session,
            ),
        )
    finally:
        event.remove(bind, "before_cursor_execute", capture_select)

    assert result.returned_count == 5
    assert result.has_more is True
    assert result.next_cursor
    assert len(statements) == 1
    assert sum("schema_columns" in statement.lower() for statement in statements) == 1

    observation = SchemaListTool().project_observation(
        status="success",
        output=result.model_dump(mode="json"),
        artifacts=[],
    )
    assert observation.facts["returned_count"] == 5
    assert [table["qualified_name"] for table in observation.facts["tables"]] == [
        table.qualified_name for table in result.tables
    ]


def test_schema_list_cursor_preserves_same_named_tables_across_schemas(
    db_session,
    test_datasource,
) -> None:
    for schema_name in ("analytics", "reporting"):
        db_session.add(
            SchemaTable(
                data_source_id=test_datasource.id,
                table_schema=schema_name,
                table_name="shared_fact",
                table_type="table",
            )
        )
    db_session.commit()
    context = ToolRunContext.for_invocation(
        request=SimpleNamespace(
            datasource_id=test_datasource.id,
            session_id="session_schema_identity",
        ),
        idempotency_key="schema-list-identity",
        resources={("dbfox.data.database", str(test_datasource.id)): db_session},
        scope_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version=1),),
        metadata_session=db_session,
    )

    first = SchemaListTool().run(
        SchemaListInput(limit=1, name_filter="shared_fact"),
        context,
    )
    second = SchemaListTool().run(
        SchemaListInput(
            cursor=first.next_cursor,
            limit=1,
            name_filter="shared_fact",
        ),
        context,
    )

    assert first.has_more is True
    assert first.next_cursor is not None
    assert [first.tables[0].qualified_name, second.tables[0].qualified_name] == [
        "analytics.shared_fact",
        "reporting.shared_fact",
    ]


def test_schema_search_deduplicates_by_full_schema_identity(
    db_session,
    test_datasource,
) -> None:
    for index, schema_name in enumerate(("analytics", "reporting"), start=1):
        db_session.add(
            SchemaSearchDoc(
                datasource_id=test_datasource.id,
                entity_type="table",
                entity_id=f"shared-{index}",
                table_schema=schema_name,
                table_name="shared_fact",
                name="shared_fact",
                search_text="shared_fact",
            )
        )
    db_session.commit()
    result = SchemaSearchTool().run(
        SchemaSearchInput(queries=["shared_fact"], limit_per_query=10),
        ToolRunContext.for_invocation(
            request=SimpleNamespace(
                datasource_id=test_datasource.id,
                session_id="session_search_identity",
            ),
            idempotency_key="schema-search-identity",
            resources={("dbfox.data.database", str(test_datasource.id)): db_session},
            scope_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version=1),),
            metadata_session=db_session,
        ),
    )

    identities = {
        (item["schema_name"], item["table_name"])
        for item in result.candidates
        if item.get("table_name") == "shared_fact"
    }
    assert identities == {
        ("analytics", "shared_fact"),
        ("reporting", "shared_fact"),
    }


def test_catalog_refresh_leaves_commit_to_tool_runtime(
    db_session,
    test_datasource,
) -> None:
    original_sync_at = test_datasource.last_sync_at
    result = CatalogRefreshTool().run(
        DatabaseTargetInput(),
        ToolRunContext.for_invocation(
            request=SimpleNamespace(
                datasource_id=test_datasource.id,
                session_id="session_catalog_refresh",
            ),
            idempotency_key="catalog-refresh",
            resources={("dbfox.data.database", str(test_datasource.id)): db_session},
            scope_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version=1),),
            metadata_session=db_session,
        ),
    )

    assert result.status == "ready"
    assert result.table_count > 0
    assert result.refreshed_at
    db_session.rollback()
    db_session.expire_all()
    assert (
        db_session.get(type(test_datasource), test_datasource.id).last_sync_at
        == original_sync_at
    )


def test_chart_intent_uses_verified_result_columns() -> None:
    suggestion = resolve_chart_suggestion(
        ChartCreateInput(
            result_artifact_id="result-1",
            intent="Compare revenue by region",
            chart_type="bar",
            x="region",
            y="revenue",
        ),
        columns=["region", "revenue"],
        rows=[
            {"region": "East", "revenue": 10},
            {"region": "West", "revenue": 20},
        ],
    )

    assert suggestion["chartable"] is True
    assert suggestion["type"] == "bar"
    assert suggestion["aggregation"] == "sum"
    assert suggestion["x"] == "region"
    assert suggestion["y"] == "revenue"


def test_chart_intent_rejects_unverified_result_columns() -> None:
    with pytest.raises(ToolInputError, match="not present"):
        resolve_chart_suggestion(
            ChartCreateInput(
                result_artifact_id="result-1",
                x="region",
                y="invented_metric",
            ),
            columns=["region", "revenue"],
            rows=[{"region": "East", "revenue": 10}],
        )


def test_chart_auto_type_uses_values_instead_of_column_name_tokens() -> None:
    assert (
        infer_chart_type(
            "bucket",
            [{"bucket": "2026-07-01"}, {"bucket": "2026-07-02"}],
        )
        == "line"
    )
    assert (
        infer_chart_type(
            "month_name_but_categorical",
            [{"month_name_but_categorical": "enterprise"}],
        )
        == "bar"
    )
    assert infer_chart_type("axis", [{"axis": 1}, {"axis": 2}]) == "scatter"


def test_result_profile_reports_quality_distribution_and_numeric_summary() -> None:
    profiles = profile_rows(
        [
            {"region": "East", "revenue": 10},
            {"region": "East", "revenue": 20},
            {"region": None, "revenue": 30},
        ],
        ["region", "revenue"],
        top_k=2,
    )

    assert profiles[0] == {
        "column": "region",
        "kind": "string",
        "sample_count": 3,
        "non_null_count": 2,
        "null_count": 1,
        "distinct_count": 1,
        "top_values": [{"value": "East", "count": 2, "share": 1.0}],
    }
    assert profiles[1]["kind"] == "number"
    assert profiles[1]["numeric"] == {
        "min": 10.0,
        "max": 30.0,
        "mean": 20.0,
        "median": 20.0,
    }


def test_result_profile_contract_rejects_duplicate_columns() -> None:
    with pytest.raises(ValueError, match="must not contain duplicates"):
        ResultProfileInput(
            result_artifact_id="result-1",
            columns=["revenue", "revenue"],
        )


def test_db_search_fallback_keyword_matches_table_and_column_names(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_search(db_session, test_datasource.id, "users", 5)
    assert result["total_matches"] >= 1
    first = result["results"][0]
    assert first["type"] in {"table", "column"}
    assert any(r.get("table_name") == "users" for r in result["results"])


def test_db_search_fallback_keyword_returns_empty_for_no_match(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_search(db_session, test_datasource.id, "xyznonexistent12345", 5)
    assert result["total_matches"] == 0
    assert result["results"] == []


@pytest.mark.parametrize(
    ("query", "limit"),
    [
        ("", 5),
        (" " * 10, 5),
        ("valid", 0),
        ("valid", 51),
        ("x" * 513, 5),
    ],
)
def test_db_search_rejects_unbounded_input(
    db_session,
    test_datasource,
    query: str,
    limit: int,
) -> None:
    with pytest.raises(ToolInputError):
        db_search(db_session, test_datasource.id, query, limit)


def test_db_search_caps_model_generated_tokens() -> None:
    query = " ".join(f"token{index}" for index in range(MAX_SEARCH_TOKENS + 10))

    assert len(_tokenize_search_query(query)) == MAX_SEARCH_TOKENS


def test_db_search_fallback_uses_schema_doc_ai_annotations(
    db_session, test_datasource
) -> None:
    db_session.add(
        SchemaSearchDoc(
            datasource_id=test_datasource.id,
            entity_type="table",
            entity_id="orders-doc",
            table_name="orders",
            name="orders",
            ai_description="Gross merchandise value (GMV) derived from paid order amount.",
            business_terms='["GMV", "gross merchandise value"]',
            aliases='["gross sales"]',
            search_text="orders GMV gross merchandise value paid order amount",
        )
    )
    db_session.commit()

    result = db_search(db_session, test_datasource.id, "GMV", 5)

    assert result["total_matches"] >= 1
    assert result["results"][0]["table_name"] == "orders"
    assert "ai_description_match:GMV" in result["results"][0]["reasons"]


def test_db_search_fallback_uses_schema_doc_semantic_fields(
    db_session, test_datasource
) -> None:
    db_session.add(
        SchemaSearchDoc(
            datasource_id=test_datasource.id,
            entity_type="table",
            entity_id="semantic-doc",
            table_name="orders",
            name="orders",
            semantic_tags='["revenue_metrics"]',
            business_terms='["GMV"]',
            aliases='["gross sales"]',
            search_text="orders",
        )
    )
    db_session.commit()

    for query in ("revenue_metrics", "GMV", "gross sales"):
        result = db_search(db_session, test_datasource.id, query, 5)

        assert result["total_matches"] >= 1
        assert result["results"][0]["table_name"] == "orders"


def test_db_search_returns_trace_fields_for_schema_discovery(
    db_session, test_datasource
) -> None:
    db_session.add(
        SchemaSearchDoc(
            datasource_id=test_datasource.id,
            entity_type="table",
            entity_id="semantic-trace-doc",
            table_name="orders",
            name="orders",
            semantic_tags='["revenue_metrics"]',
            business_terms='["GMV"]',
            aliases='["gross sales"]',
            search_text="orders",
        )
    )
    db_session.commit()

    result = db_search(db_session, test_datasource.id, "revenue_metrics", 5)

    assert result["original_query"] == "revenue_metrics"
    assert result["tokens"] == ["revenue_metrics"]
    assert "semantic_tags" in result["searched_fields"]
    assert "business_terms" in result["searched_fields"]
    assert "aliases" in result["searched_fields"]
    assert result["matched_fields"] == ["semantic_tags"]
    assert result["results"][0]["matched_fields"] == ["semantic_tags"]


def test_db_inspect_reads_live_sqlite_table_structure(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_inspect(db_session, test_datasource.id, ["orders"])[0]
    assert result.object_type == "table"
    assert result.name == "orders"
    assert any(
        column.name == "user_id"
        and column.foreign_key
        and column.foreign_key.table == "users"
        for column in result.columns
    )
    assert any(
        foreign_key.column == "user_id" for foreign_key in result.foreign_keys_out
    )


def test_db_inspect_reads_live_sqlite_column(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_inspect(db_session, test_datasource.id, ["orders.user_id"])[0]
    assert result.object_type == "column"
    assert result.table == "orders"
    assert result.name == "user_id"
    assert result.type == "INTEGER"
    assert result.primary_key is False
    assert result.foreign_key is not None
    assert result.foreign_key.table == "users"
    assert result.foreign_key.column == "id"


def test_db_preview_limits_columns_rows_and_masks_sensitive_values(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_preview(
        db_session,
        test_datasource.id,
        table="users",
        columns=["id", "email", "phone"],
        limit=50,
    )
    assert result["table"] == "users"
    assert result["columns"] == ["id", "email", "phone"]
    assert result["limit_applied"] == 20
    assert result["returned_rows"] <= 20
    assert result["rows"][0]["email"] == "[REDACTED]"
    assert "column_summaries" in result
    assert (
        db_session.query(QueryHistory)
        .filter(QueryHistory.data_source_id == test_datasource.id)
        .count()
        == 1
    )


def test_db_preview_accepts_schema_list_qualified_table_name(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)

    result = db_preview(
        db_session,
        test_datasource.id,
        table="main.users",
        columns=["id"],
        limit=5,
    )

    assert result["table"] == "main.users"
    assert result["returned_rows"] > 0
    assert 'FROM "main"."users"' in result["safe_sql"]


def test_db_preview_rejects_ambiguous_unqualified_table_name(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)
    db_session.add(
        SchemaTable(
            data_source_id=test_datasource.id,
            table_schema="shadow",
            table_name="users",
            table_type="table",
        )
    )
    db_session.flush()

    with pytest.raises(ToolInputError, match="Ambiguous table name"):
        db_preview(
            db_session,
            test_datasource.id,
            table="users",
            columns=["id"],
            limit=5,
        )


def test_db_preview_quotes_spider_style_column_names(
    db_session, test_datasource
) -> None:
    conn = sqlite3.connect(test_datasource.database_name)
    try:
        conn.execute(
            "CREATE TABLE spider_ratings ("
            '"18_49_Rating_Share" REAL, '
            '"Official_ratings_(millions)" REAL'
            ")"
        )
        conn.execute(
            'INSERT INTO spider_ratings ("18_49_Rating_Share", "Official_ratings_(millions)") VALUES (?, ?)',
            (4.2, 7.5),
        )
        conn.commit()
    finally:
        conn.close()

    sync_schema(db_session, test_datasource.id)

    result = db_preview(
        db_session,
        test_datasource.id,
        table="spider_ratings",
        columns=["18_49_Rating_Share", "Official_ratings_(millions)"],
        limit=5,
    )

    assert result["columns"] == ["18_49_Rating_Share", "Official_ratings_(millions)"]
    assert result["returned_rows"] == 1
    assert float(result["rows"][0]["18_49_Rating_Share"]) == 4.2
    assert float(result["rows"][0]["Official_ratings_(millions)"]) == 7.5
    assert '"18_49_Rating_Share"' in result["safe_sql"]


def test_db_preview_rejects_unknown_columns_before_query(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)
    with pytest.raises(ToolInputError, match=r"Column\(s\) not found"):
        db_preview(db_session, test_datasource.id, table="users", columns=["missing"])
    assert db_session.query(QueryHistory).count() == 0


def test_data_preview_runtime_returns_actionable_safe_input_error(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)

    result = ToolRuntime(build_product_tool_registry()).invoke(
        tool_name="data_preview",
        raw_input={"table": "main.users", "columns": ["missing"], "limit": 5},
        request=SimpleNamespace(
            datasource_id=str(test_datasource.id),
            datasource_generation=1,
        ),
        idempotency_key="preview-invalid-column",
        resources={("dbfox.data.database", str(test_datasource.id)): db_session},
        scope_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version=1),),
        metadata_session=db_session,
    )

    assert result.status == "failed"
    assert result.error_code == "TOOL_INPUT_ERROR"
    assert result.output is not None
    assert result.output["status"] == "failed"
    assert result.output["error_code"] == "TOOL_INPUT_ERROR"
    safe_message = str(result.output["safe_message"])
    assert safe_message.startswith("Column(s) not found in main.users: missing.")
    assert "Available columns:" in safe_message
    assert "id" in safe_message
    assert "Column(s) not found" in str(result.error)
    assert db_session.query(QueryHistory).count() == 0


def test_schema_inspection_budget_preserves_each_target_and_column_evidence() -> None:
    inspections = [
        {
            "target": f"table_{table_index}",
            "details": {
                "object_type": "table",
                "name": f"table_{table_index}",
                "schema_name": "main",
                "type": "table",
                "dialect": "sqlite",
                "columns": [
                    {
                        "name": f"column_{column_index}",
                        "type": "TEXT",
                        "nullable": True,
                        "default": None,
                        "primary_key": False,
                        "foreign_key": None,
                        "comment": "x" * 80,
                    }
                    for column_index in range(500)
                ],
                "primary_key": [],
                "foreign_keys_out": [],
                "foreign_keys_in": [],
                "indexes": [],
                "source": "live",
            },
        }
        for table_index in range(5)
    ]

    facts = (
        SchemaInspectTool()
        .project_observation(
            status="success",
            output={"inspections": inspections},
            artifacts=[],
        )
        .facts
    )

    assert byte_size(facts) <= 32_768
    assert [item["target"] for item in facts["inspections"]] == [
        f"table_{index}" for index in range(5)
    ]
    assert all(item["details"]["column_count"] == 500 for item in facts["inspections"])
    assert all(item["details"]["columns"] for item in facts["inspections"])
    assert all(item["details"]["columns_truncated"] for item in facts["inspections"])


def test_sql_lifecycle_validates_and_executes_readonly_sql(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)
    safety = sql_validate(
        db_session,
        test_datasource.id,
        "SELECT id, email FROM users",
        question="count users",
    )
    result = sql_execute_readonly(
        db_session,
        test_datasource.id,
        question="count users",
        safety=safety["execution_safety_decision"],
    )
    assert result["status"] == "success"
    assert result["columns"] == ["id", "email"]
    assert result["returned_rows"] >= 1
    assert result["audit"]["readonly_checked"] is True
    assert result["audit"]["limit_injected"] is True
    assert "LIMIT" in result["safe_sql"].upper()


def test_sql_lifecycle_blocks_writes_inside_execute_tool(
    db_session, test_datasource
) -> None:
    sync_schema(db_session, test_datasource.id)
    safety = sql_validate(db_session, test_datasource.id, "DELETE FROM users")
    with pytest.raises(GuardrailValidationError):
        sql_execute_readonly(
            db_session,
            test_datasource.id,
            safety=safety["execution_safety_decision"],
        )
