from __future__ import annotations

import pytest

from engine.agent import AgentRunRequest
from engine.agent.tools import (
    build_query_plan_tool,
    generate_sql_tool,
    suggest_chart_tool,
    validate_sql_tool,
)
from engine.schema_sync import sync_schema


def test_build_query_plan_tool_for_chinese_question(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="统计每天订单量")

    obs = build_query_plan_tool(db_session, req, {"schema_context": "", "selected_tables": ["orders"]})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["analysis_goal"]
    assert "orders" in obs.output["candidate_tables"]


def test_generate_sql_tool_rewrites_select_star(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT * FROM users",
            "model": "test",
            "mode": "offline",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools.generate_sql", fake_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="查询所有用户")

    obs = generate_sql_tool(db_session, req)

    assert obs.status == "success"
    assert obs.output is not None
    assert "SELECT *" not in obs.output["sql"].upper()
    assert "users.id" in obs.output["sql"]
    assert "LIMIT" in obs.output["sql"].upper()
    assert "select_star_rewritten_to_explicit_columns" in obs.output["rewrite_notes"]


@pytest.mark.parametrize("sql", ["DELETE FROM users", "UPDATE users SET role = 'admin'", "DROP TABLE users"])
def test_validate_sql_tool_blocks_write_operations(db_session, demo_datasource, sql: str) -> None:
    sync_schema(db_session, demo_datasource.id)

    obs = validate_sql_tool(db_session, demo_datasource.id, sql)

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["can_execute"] is False
    assert obs.output["guardrail"]["result"] == "reject"


def test_validate_sql_tool_blocks_unrewritten_select_star(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)

    obs = validate_sql_tool(db_session, demo_datasource.id, "SELECT * FROM users")

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["can_execute"] is False
    assert "explicit column" in obs.output["revise_suggestion"]


def test_suggest_chart_category_numeric_returns_bar() -> None:
    obs = suggest_chart_tool(
        {
            "success": True,
            "columns": ["category", "count"],
            "rows": [{"category": "A", "count": "2"}, {"category": "B", "count": "5"}],
            "rowCount": 2,
        }
    )

    assert obs.status == "success"
    assert obs.output == {
        "type": "bar",
        "x": "category",
        "y": "count",
        "reason": "A category field plus a numeric measure is best compared by category.",
    }
