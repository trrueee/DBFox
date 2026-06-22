from __future__ import annotations

from engine.agent_core.artifacts import (
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
    )

    assert artifact.payload["rowCount"] == 128
    assert artifact.payload["returnedRows"] == 2
    assert artifact.payload["latencyMs"] == 42
    assert artifact.payload["truncated"] is True
    assert artifact.payload["warnings"] == ["backend limit reached"]
    assert artifact.payload["notices"] == ["preview only"]
    assert artifact.payload["previewRowCount"] == 2
    assert artifact.payload["datasourceId"] == "ds_123"
    assert artifact.payload["storageMode"] == "payload"


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
