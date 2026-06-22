from __future__ import annotations

from engine.agent_core.artifacts import (
    build_chart_artifact,
    build_sql_artifact,
    build_table_artifact,
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


def test_table_artifact_preserves_result_browsing_metadata():
    artifact = build_table_artifact(
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
        safety=None,
    )

    assert artifact.payload["rowCount"] == 128
    assert artifact.payload["returnedRows"] == 2
    assert artifact.payload["latencyMs"] == 42
    assert artifact.payload["truncated"] is True
    assert artifact.payload["warnings"] == ["backend limit reached"]
    assert artifact.payload["notices"] == ["preview only"]
    assert artifact.payload["used_tables"] == ["orders"]


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
