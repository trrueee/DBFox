from __future__ import annotations

from engine.agent_kernel.lifecycle import critique_sql, reflect


def test_sql_critic_requests_revision_when_query_plan_table_is_missing() -> None:
    state = {
        "messages": [{"role": "user", "content": "查一下订单 GMV"}],
        "last_tool_name": "sql.generate",
        "sql": "SELECT SUM(amount) FROM transactions",
        "query_plan": {"candidate_tables": ["orders"], "metrics": [{"name": "gmv"}]},
    }

    critique = critique_sql(state)
    reflection = reflect(state)

    assert critique["needs_revision"] is True
    assert any("candidate table" in issue for issue in critique["issues"])
    assert reflection["action"] == "revise_sql"
    assert reflection["sql_critique"]["needs_revision"] is True


def test_sql_critic_passes_reasonable_grouped_metric_sql() -> None:
    state = {
        "messages": [{"role": "user", "content": "按城市统计 GMV"}],
        "last_tool_name": "sql.generate",
        "sql": "SELECT city, SUM(gmv) AS total_gmv FROM orders GROUP BY city",
        "query_plan": {
            "candidate_tables": ["orders"],
            "metrics": [{"name": "gmv"}],
            "dimensions": [{"name": "city"}],
        },
    }

    critique = critique_sql(state)
    reflection = reflect(state)

    assert critique["needs_revision"] is False
    assert critique["status"] == "passed"
    assert reflection["action"] == "continue"
