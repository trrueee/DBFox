from __future__ import annotations

from engine.agent_core.artifacts import (
    AgentArtifactIdentity,
    build_agent_artifacts,
    build_chart_artifact,
    build_sql_artifact,
    build_result_view_artifact,
)


def test_sql_artifact_includes_purpose_used_tables_and_status_metadata():
    artifact = build_sql_artifact(
        "SELECT DATE(created_at) AS day, COUNT(*) FROM orders GROUP BY DATE(created_at)",
        safety={
            "passed": True,
            "can_execute": True,
            "execution": {"rowCount": 12, "latencyMs": 42},
        },
    )

    assert artifact.payload["purpose"] == "分析查询"
    assert artifact.payload["used_tables"] == ["orders"]
    assert artifact.payload["validation_status"] == "passed"
    assert artifact.payload["execution_status"] == "completed"
    assert artifact.payload["rowCount"] == 12
    assert artifact.payload["latencyMs"] == 42


def test_result_view_artifact_preserves_result_browsing_metadata():
    artifact = build_result_view_artifact(
        {
            "success": True,
            "columns": ["day", "order_count"],
            "rows": [
                {"day": "2026-06-01", "order_count": 10},
                {"day": "2026-06-02", "order_count": 20},
            ],
            "rowCount": 128,
            "returnedRows": 2,
            "latencyMs": 42,
            "truncated": True,
            "warnings": ["backend limit reached"],
            "notices": ["preview only"],
            "sql": "SELECT DATE(created_at) AS day, COUNT(*) AS order_count FROM orders GROUP BY DATE(created_at)",
        },
        datasource_id="ds_123",
        safety=None,
        source_sql_artifact_id="sql-artifact-metadata",
        source_sql_semantic_id="sql_candidate_metadata",
    )

    assert artifact.payload["rowCount"] == 128
    assert artifact.payload["returnedRows"] == 2
    assert artifact.payload["latencyMs"] == 42
    assert artifact.payload["truncated"] is True
    assert artifact.payload["warnings"] == ["backend limit reached"]
    assert artifact.payload["notices"] == ["preview only"]
    assert artifact.payload["previewRowCount"] == 2
    assert artifact.payload["datasourceId"] == "ds_123"
    assert artifact.payload["storageMode"] == "sql_backed"
    assert artifact.payload["previewRows"] == [
        {"day": "2026-06-01", "order_count": 10},
        {"day": "2026-06-02", "order_count": 20},
    ]
    assert "rows" not in artifact.payload


def test_result_view_artifact_stores_typed_columns_dialect_and_fingerprint():
    artifact = build_result_view_artifact(
        {
            "success": True,
            "columns": [
                {"name": "id", "type": "integer"},
                {"name": "name", "type": "text"},
            ],
            "rows": [{"id": 1, "name": "Alice"}],
            "rowCount": 1,
            "latencyMs": 12,
            "sql": "SELECT id, name FROM users",
            "dialect": "sqlite",
        },
        datasource_id="ds_123",
        safety={"can_execute": True},
        source_sql_artifact_id="sql-artifact-preview",
        source_sql_semantic_id="sql_candidate_preview",
    )

    assert artifact.payload["safeSql"] == "SELECT id, name FROM users"
    assert artifact.payload["dialect"] == "sqlite"
    assert artifact.payload["columns"] == [
        {"name": "id", "type": "integer"},
        {"name": "name", "type": "text"},
    ]
    assert artifact.payload["fingerprint"].startswith("sql_")
    assert artifact.payload["sqlFingerprint"] == artifact.payload["fingerprint"]


def test_result_view_artifact_keeps_preview_not_full_rows():
    artifact = build_result_view_artifact(
        {
            "success": True,
            "columns": ["id"],
            "rows": [{"id": index} for index in range(100)],
            "rowCount": 100,
            "returnedRows": 100,
            "latencyMs": 12,
            "sql": "SELECT id FROM users",
        },
        datasource_id="ds_123",
        safety={"can_execute": True},
        source_sql_artifact_id="sql-artifact-preview-full",
        source_sql_semantic_id="sql_candidate_preview_full",
    )

    assert artifact.payload["storageMode"] == "sql_backed"
    assert len(artifact.payload["previewRows"]) == 10
    assert artifact.payload["previewRowCount"] == 10
    assert artifact.payload["rowCount"] == 100
    assert artifact.payload["returnedRows"] == 100
    assert "rows" not in artifact.payload


def test_agent_artifacts_bind_result_view_to_emitted_sql_and_safety_ids():
    artifacts = build_agent_artifacts(
        query_plan=None,
        sql="SELECT id, amount FROM orders",
        safety={
            "passed": True,
            "can_execute": True,
            "safe_sql": "SELECT id, amount FROM orders",
        },
        execution={
            "success": True,
            "columns": ["id", "amount"],
            "rows": [{"id": 1, "amount": 20}],
            "rowCount": 1,
            "safe_sql": "SELECT id, amount FROM orders",
        },
        chart_suggestion=None,
        answer=None,
        datasource_id="ds-orders",
        identity=AgentArtifactIdentity("run-chain"),
    )

    sql_artifact = next(artifact for artifact in artifacts if artifact.type == "sql")
    safety_artifact = next(artifact for artifact in artifacts if artifact.type == "safety")
    result_view = next(artifact for artifact in artifacts if artifact.type == "result_view")

    assert result_view.depends_on == [sql_artifact.id, safety_artifact.id]
    assert safety_artifact.depends_on == [sql_artifact.id]
    assert result_view.payload["sourceSqlArtifactKey"] == sql_artifact.id
    assert result_view.payload["sourceSqlSemanticKey"] == sql_artifact.semantic_id
    assert result_view.payload["safetyArtifactKey"] == safety_artifact.id
    assert result_view.payload["safetySemanticKey"] == safety_artifact.semantic_id


def test_chart_artifact_links_metrics_to_source_fields():
    artifact = build_chart_artifact(
        {
            "type": "bar",
            "x": "day",
            "y": "gmv",
            "metrics": [{"name": "GMV", "expression": "SUM(orders.amount)", "source_column": "orders.amount"}],
            "dimensions": [{"name": "日期", "column": "orders.created_at", "transform": "DATE"}],
        },
        safety=None,
        execution={"sql": "SELECT DATE(created_at) AS day, SUM(amount) AS gmv FROM orders GROUP BY DATE(created_at)"},
    )

    assert artifact.payload["source_refs"] == [
        {"label": "GMV", "formula": "SUM(orders.amount)", "field": "orders.amount"},
        {"label": "日期", "formula": "DATE(orders.created_at)", "field": "orders.created_at"},
    ]


def test_chart_artifact_exposes_normalized_chart_contract_fields():
    artifact = build_chart_artifact(
        {
            "type": "pie",
            "x": "user_type",
            "y": "gmv",
            "aggregation": "sum",
            "reason": "展示 GMV 构成",
            "series": [
                {"label": "personal", "value": 120},
                {"label": "enterprise", "value": 80},
            ],
        },
        safety={"can_execute": True},
        execution={"sql": "SELECT user_type, SUM(amount) AS gmv FROM orders GROUP BY user_type"},
    )

    assert artifact.payload["type"] == "pie"
    assert artifact.payload["chart_type"] == "pie"
    assert artifact.payload["x"] == "user_type"
    assert artifact.payload["y"] == "gmv"
    assert artifact.payload["aggregation"] == "sum"
    assert artifact.payload["reason"] == "展示 GMV 构成"
    assert artifact.payload["series"] == [
        {"label": "personal", "value": 120},
        {"label": "enterprise", "value": 80},
    ]


def test_chart_artifact_depends_on_result_view_for_same_sql():
    artifact = build_chart_artifact(
        {
            "type": "bar",
            "x": "day",
            "y": "gmv",
            "series": [{"label": "2026-06-01", "value": 120}],
        },
        safety={"can_execute": True},
        execution={"sql": "SELECT day, SUM(amount) AS gmv FROM orders GROUP BY day"},
    )

    assert artifact.depends_on[0].startswith("result_view_")


def test_agent_artifacts_skip_non_chartable_chart_suggestions():
    artifacts = build_agent_artifacts(
        query_plan=None,
        sql=None,
        safety=None,
        execution=None,
        chart_suggestion={"type": "none", "chartable": False, "series": []},
        answer=None,
    )

    assert all(artifact.type != "chart" for artifact in artifacts)
