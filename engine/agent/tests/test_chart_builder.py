from __future__ import annotations

from engine.agent_core.chart_builder import suggest_plotly_chart


def test_chart_suggestion_includes_explainable_metadata_for_category_metric_pair():
    suggestion = suggest_plotly_chart(
        {
            "success": True,
            "columns": ["status", "gmv"],
            "rows": [
                {"status": "paid", "gmv": 120},
                {"status": "paid", "gmv": 80},
                {"status": "refunded", "gmv": 20},
            ],
        }
    )

    assert suggestion["type"] == "bar"
    assert suggestion["x"] == "status"
    assert suggestion["y"] == "gmv"
    assert suggestion["x_label"] == "status"
    assert suggestion["y_label"] == "gmv"
    assert suggestion["series_label"] == "gmv"
    assert suggestion["data_label"] is True
    assert suggestion["sample_size"] == 3
    assert suggestion["dimensions"] == [
        {"name": "status", "column": "status", "role": "x", "kind": "category"}
    ]
    assert suggestion["metrics"] == [
        {"name": "gmv", "source_column": "gmv", "expression": "SUM(gmv)", "aggregation": "sum", "role": "y"}
    ]
    assert suggestion["series"] == [
        {"label": "paid", "value": 200.0},
        {"label": "refunded", "value": 20.0},
    ]


def test_chart_suggestion_includes_temporal_axis_metadata_for_time_series():
    suggestion = suggest_plotly_chart(
        {
            "success": True,
            "columns": ["created_date", "orders"],
            "rows": [
                {"created_date": "2026-06-01", "orders": 10},
                {"created_date": "2026-06-02", "orders": 12},
            ],
        }
    )

    assert suggestion["type"] == "line"
    assert suggestion["dimensions"][0]["kind"] == "temporal"
    assert suggestion["metrics"][0]["expression"] == "SUM(orders)"
    assert suggestion["aggregation"] == "sum"
    assert suggestion["sample_size"] == 2


def test_chart_suggestion_uses_none_type_when_result_is_not_chartable():
    suggestion = suggest_plotly_chart(
        {
            "success": True,
            "columns": ["first_name", "last_name"],
            "rows": [
                {"first_name": "Ada", "last_name": "Lovelace"},
                {"first_name": "Grace", "last_name": "Hopper"},
            ],
        }
    )

    assert suggestion["type"] == "none"
    assert suggestion["chartable"] is False
    assert suggestion["series"] == []
