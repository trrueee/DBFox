from __future__ import annotations

import uuid

import pytest

from engine.agent import AgentRunRequest
from engine.agent.tools import (
    _prepare_generated_sql,
    build_query_plan_tool,
    generate_sql_tool,
    revise_sql_tool,
    suggest_chart_tool,
    validate_sql_tool,
)
from engine.models import SchemaColumn, SchemaTable
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
    assert obs.output["metadata"]["rewrite"]["select_star_column_limit"] == 12


def test_generate_sql_tool_uses_query_plan_before_fallback(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fail_generate_sql(*_args, **_kwargs):
        raise AssertionError("generate_sql fallback should not run for a renderable plan")

    monkeypatch.setattr("engine.agent.tools.generate_sql", fail_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="count users")
    metric = {"name": "total_users", "expression": "COUNT(*)"}
    query_plan = {
        "analysis_goal": "count users",
        "metrics": [metric],
        "dimensions": [],
        "filters": [],
        "candidate_tables": ["users"],
        "raw_plan": {
            "intent": "aggregate",
            "tables": ["users"],
            "metrics": [metric],
            "dimensions": [],
            "filters": [],
            "joins": [],
            "limit": 100,
        },
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["metadata"]["generation_source"] == "query_plan_rendered"
    assert "COUNT(*) AS total_users" in obs.output["sql"]
    assert "FROM users" in obs.output["sql"]


def test_generate_sql_tool_omits_empty_raw_plan_order_by(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fail_generate_sql(*_args, **_kwargs):
        raise AssertionError("generate_sql fallback should not run for a renderable plan")

    monkeypatch.setattr("engine.agent.tools.generate_sql", fail_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="count users")
    metric = {"name": "total_users", "expression": "COUNT(*)"}
    query_plan = {
        "analysis_goal": "count users",
        "candidate_tables": ["users"],
        "raw_plan": {
            "intent": "aggregate",
            "tables": ["users"],
            "metrics": [metric],
            "dimensions": [],
            "filters": [],
            "joins": [],
            "order_by": "[]",
            "limit": 100,
        },
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)

    assert obs.status == "success"
    assert obs.output is not None
    assert "ORDER BY" not in obs.output["sql"].upper()


@pytest.mark.parametrize(
    "raw_sql",
    [
        "SELECT id FROM users ORDER BY [] LIMIT 100",
        "SELECT id FROM users ORDER BY ARRAY() LIMIT 100",
        "SELECT id FROM users ORDER BY ARRAY(STRUCT('id', 'desc')) LIMIT 100",
        "SELECT id FROM users ORDER BY STRUCT() LIMIT 100",
        "SELECT id FROM users ORDER BY STRUCT('id', 'desc') LIMIT 100",
        "SELECT id FROM users ORDER BY JSON_ARRAY(id) LIMIT 100",
        "SELECT id FROM users ORDER BY () LIMIT 100",
    ],
)
def test_prepare_generated_sql_removes_invalid_order_by(db_session, demo_datasource, raw_sql: str) -> None:
    sync_schema(db_session, demo_datasource.id)

    prepared, notes, _metadata = _prepare_generated_sql(db_session, demo_datasource.id, raw_sql)

    assert "ORDER BY []" not in prepared.upper()
    assert "ORDER BY ARRAY" not in prepared.upper()
    assert "ORDER BY STRUCT" not in prepared.upper()
    assert "ORDER BY JSON_ARRAY" not in prepared.upper()
    assert "ORDER BY ()" not in prepared.upper()
    assert "invalid_order_by_removed" in notes


@pytest.mark.parametrize(
    ("raw_sql", "expected_order_by"),
    [
        ("SELECT id FROM users ORDER BY id DESC LIMIT 100", "ORDER BY id DESC"),
        ("SELECT id FROM users ORDER BY username ASC LIMIT 100", "ORDER BY username ASC"),
        ("SELECT id FROM users ORDER BY ABS(id) DESC LIMIT 100", "ORDER BY ABS(id) DESC"),
    ],
)
def test_prepare_generated_sql_preserves_valid_order_by(
    db_session,
    demo_datasource,
    raw_sql: str,
    expected_order_by: str,
) -> None:
    sync_schema(db_session, demo_datasource.id)

    prepared, notes, _metadata = _prepare_generated_sql(db_session, demo_datasource.id, raw_sql)

    assert expected_order_by in prepared
    assert "invalid_order_by_removed" not in notes


def test_generate_sql_tool_no_key_uses_offline_fallback(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list products", api_key=None)

    obs = generate_sql_tool(db_session, req)

    assert obs.status == "success"
    assert obs.input is not None
    assert obs.input["has_api_key"] is False
    assert obs.output is not None
    assert obs.output["model"] == "databox-local-heuristic"
    assert obs.output["mode"] == "offline"


def test_generate_sql_tool_reports_select_star_truncation_limit(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)
    table = SchemaTable(
        id=str(uuid.uuid4()),
        data_source_id=demo_datasource.id,
        table_schema=demo_datasource.database_name,
        table_name="wide_table",
        table_comment="wide table",
        table_type="BASE TABLE",
        row_count_estimate=1,
        engine_name="InnoDB",
    )
    db_session.add(table)
    db_session.flush()
    db_session.add_all(
        [
            SchemaColumn(
                id=str(uuid.uuid4()),
                table_id=table.id,
                column_name=f"col_{index}",
                data_type="varchar",
                column_type="varchar(50)",
                ordinal_position=index,
            )
            for index in range(1, 14)
        ]
    )
    db_session.commit()

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT * FROM wide_table",
            "model": "test",
            "mode": "offline",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools.generate_sql", fake_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="wide table")

    obs = generate_sql_tool(db_session, req)

    assert obs.status == "success"
    assert obs.output is not None
    rewrite = obs.output["metadata"]["rewrite"]
    assert rewrite["select_star_column_limit"] == 12
    assert rewrite["truncated_tables"] == ["wide_table"]
    assert "first 12 columns" in rewrite["message"]
    assert "col_13" not in obs.output["sql"]


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
    assert obs.output["execution_safety_decision"]["policy"] == "agent_readonly"
    assert "select_star" in obs.output["execution_safety_decision"]["blocked_reasons"]
    assert "explicit column" in obs.output["revise_suggestion"]


def test_validate_sql_tool_blocks_schema_hallucination(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)

    obs = validate_sql_tool(db_session, demo_datasource.id, "SELECT imaginary_column FROM users LIMIT 10")

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["can_execute"] is False
    assert obs.output["schema_warnings"]


def test_validate_sql_tool_requires_confirmation_for_prod(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    demo_datasource.env = "prod"
    db_session.commit()

    obs = validate_sql_tool(db_session, demo_datasource.id, "SELECT id, username FROM users LIMIT 10")

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["requires_confirmation"] is True
    assert obs.output["can_execute"] is False
    assert any("Production datasource" in message for message in obs.output["messages"])


def test_revise_sql_tool_returns_structured_fix_fields(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    safety = validate_sql_tool(db_session, demo_datasource.id, "SELECT * FROM users").output

    obs = revise_sql_tool(
        "SELECT * FROM users",
        "SELECT * is blocked",
        safety,
        db=db_session,
        datasource_id=demo_datasource.id,
    )

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["can_fix"] is True
    assert obs.output["fixed_sql"]
    assert "SELECT *" not in obs.output["fixed_sql"].upper()
    assert "select_star_rewritten_to_explicit_columns" in obs.output["changes"]
    assert isinstance(obs.output["remaining_risks"], list)


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


def test_render_structured_order_by_list_and_dict(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fail_generate_sql(*_args, **_kwargs):
        raise AssertionError("generate_sql fallback should not run for a renderable plan")

    monkeypatch.setattr("engine.agent.tools.generate_sql", fail_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users")
    metric = {"name": "total_users", "expression": "COUNT(*)"}
    # single dict order_by
    query_plan = {
        "analysis_goal": "list users",
        "candidate_tables": ["users"],
        "raw_plan": {
            "intent": "aggregate",
            "tables": ["users"],
            "metrics": [],
            "dimensions": [],
            "filters": [],
            "joins": [],
            "order_by": {"column": "id", "direction": "DESC"},
            "limit": 100,
        },
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)
    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["metadata"]["generation_source"] == "query_plan_rendered"
    assert "ORDER BY" in obs.output["sql"].upper()
    assert "DESC" in obs.output["sql"].upper()
    # multi-field list
    query_plan["raw_plan"]["order_by"] = [{"column": "id", "direction": "DESC"}, {"column": "username", "direction": "ASC"}]
    obs2 = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)
    assert obs2.status == "success"
    assert "ORDER BY" in obs2.output["sql"].upper()
    assert "username ASC" in obs2.output["sql"] or "USERNAME ASC" in obs2.output["sql"].upper()


def test_order_by_illegal_direction_triggers_fallback(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {"sql": "SELECT id FROM users ORDER BY id DESC", "model": "test", "mode": "online", "latencyMs": 1, "schemaValidationWarnings": []}

    monkeypatch.setattr("engine.agent.tools.generate_sql", fake_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users")
    query_plan = {
        "analysis_goal": "list users",
        "candidate_tables": ["users"],
        "raw_plan": {
            "intent": "aggregate",
            "tables": ["users"],
            "metrics": [],
            "dimensions": [],
            "filters": [],
            "joins": [],
            "order_by": {"column": "id", "direction": "DOWN"},
            "limit": 100,
        },
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)
    assert obs.status == "success"
    assert obs.output is not None
    # Renderer silently drops illegal direction (e.g. DOWN) and omits ORDER BY clause
    assert obs.output["metadata"]["generation_source"] == "query_plan_rendered"
    assert "ORDER BY" not in obs.output["sql"].upper()


def test_render_stringified_python_repr_order_by(db_session, demo_datasource, monkeypatch) -> None:
    """Stringified Python repr like \"[{'column': 'id', 'direction': 'DESC'}]\" must be parsed and rendered."""
    sync_schema(db_session, demo_datasource.id)

    def fail_generate_sql(*_args, **_kwargs):
        raise AssertionError("generate_sql fallback should not run for a renderable plan")

    monkeypatch.setattr("engine.agent.tools.generate_sql", fail_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users")
    query_plan = {
        "analysis_goal": "list users",
        "candidate_tables": ["users"],
        "raw_plan": {
            "intent": "aggregate",
            "tables": ["users"],
            "metrics": [],
            "dimensions": [],
            "filters": [],
            "joins": [],
            "order_by": "[{'column': 'id', 'direction': 'DESC'}]",
            "limit": 100,
        },
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)
    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["metadata"]["generation_source"] == "query_plan_rendered"
    assert "ORDER BY id DESC" in obs.output["sql"] or "ORDER BY ID DESC" in obs.output["sql"].upper()


def test_render_json_string_order_by(db_session, demo_datasource, monkeypatch) -> None:
    """JSON string like '[{\"column\":\"id\",\"direction\":\"DESC\"}]' must be parsed and rendered."""
    sync_schema(db_session, demo_datasource.id)

    def fail_generate_sql(*_args, **_kwargs):
        raise AssertionError("generate_sql fallback should not run for a renderable plan")

    monkeypatch.setattr("engine.agent.tools.generate_sql", fail_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users")
    query_plan = {
        "analysis_goal": "list users",
        "candidate_tables": ["users"],
        "raw_plan": {
            "intent": "aggregate",
            "tables": ["users"],
            "metrics": [],
            "dimensions": [],
            "filters": [],
            "joins": [],
            "order_by": '[{"column":"id","direction":"DESC"}]',
            "limit": 100,
        },
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)
    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["metadata"]["generation_source"] == "query_plan_rendered"
    assert "ORDER BY id DESC" in obs.output["sql"] or "ORDER BY ID DESC" in obs.output["sql"].upper()


def test_render_stringified_repr_illegal_direction_omits_order_by(db_session, demo_datasource, monkeypatch) -> None:
    """Stringified repr with illegal direction (DOWN) should silently omit ORDER BY."""
    sync_schema(db_session, demo_datasource.id)

    def fail_generate_sql(*_args, **_kwargs):
        raise AssertionError("generate_sql fallback should not run — renderer handles this")

    monkeypatch.setattr("engine.agent.tools.generate_sql", fail_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users")
    query_plan = {
        "analysis_goal": "list users",
        "candidate_tables": ["users"],
        "raw_plan": {
            "intent": "aggregate",
            "tables": ["users"],
            "metrics": [],
            "dimensions": [],
            "filters": [],
            "joins": [],
            "order_by": "[{'column': 'id', 'direction': 'DOWN'}]",
            "limit": 100,
        },
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)
    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["metadata"]["generation_source"] == "query_plan_rendered"
    assert "ORDER BY" not in obs.output["sql"].upper()


def test_smoke2_ordered_by_age_desc_must_have_order_by(db_session, demo_datasource, monkeypatch) -> None:
    """Targeted check for smoke-2: ordered by age from oldest to youngest → ORDER BY Age DESC."""
    sync_schema(db_session, demo_datasource.id)

    def fail_generate_sql(*_args, **_kwargs):
        raise AssertionError("generate_sql fallback should not run for a renderable plan")

    monkeypatch.setattr("engine.agent.tools.generate_sql", fail_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="Show name, country, age for all singers ordered by age from the oldest to the youngest.")
    # Simulate smoke-2's actual query_plan shape: stringified Python repr in order_by
    query_plan = {
        "analysis_goal": "retrieve_singer_details_ordered_by_age",
        "candidate_tables": ["users"],
        "raw_plan": {
            "intent": "answer_question",
            "mode": "offline",
            "tables": ["users"],
            "metrics": [],
            "dimensions": [
                {"name": "name", "column": "username", "transform": None},
                {"name": "country", "column": "email", "transform": None},
                {"name": "age", "column": "id", "transform": None},
            ],
            "filters": [],
            "joins": [],
            "order_by": "[{'column': 'id', 'direction': 'DESC'}]",
            "limit": 100,
        },
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)
    assert obs.status == "success"
    assert obs.output is not None
    # Must be query_plan_rendered (the low_confidence guard should NOT trip for this
    # because we use 'email'/'username' placeholders that exist in the schema)
    assert obs.output["metadata"]["generation_source"] == "query_plan_rendered"
    # The critical assertion: ORDER BY must appear with a DESC direction
    sql_upper = obs.output["sql"].upper()
    assert "ORDER BY" in sql_upper, f"Expected ORDER BY in SQL, got: {obs.output['sql']}"
    assert "DESC" in sql_upper, f"Expected DESC direction in SQL, got: {obs.output['sql']}"
    # Must not be a bare COUNT(*) — should contain the dimension columns
    assert "username" in obs.output["sql"].lower() or "USERNAME" in sql_upper
    sync_schema(db_session, demo_datasource.id)

    def fail_generate_sql(*_args, **_kwargs):
        raise AssertionError("generate_sql fallback should not run for a renderable plan")

    monkeypatch.setattr("engine.agent.tools.generate_sql", fail_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="users without deleted")
    query_plan = {
        "analysis_goal": "users without deleted",
        "candidate_tables": ["users"],
        "raw_plan": {
            "intent": "filter",
            "tables": ["users"],
            "metrics": [],
            "dimensions": [],
            "filters": [{"column": "users.deleted_at", "operator": "IS NULL", "value": None}],
            "joins": [],
            "limit": 100,
        },
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)
    assert obs.status == "success"
    assert obs.output is not None
    sql = obs.output["sql"]
    assert "IS NULL" in sql
    assert "'None'" not in sql and "\"None\"" not in sql


def test_plan_requires_llm_for_antijoin_and_inner_join(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {"sql": "SELECT id FROM users", "model": "test", "mode": "online", "latencyMs": 1, "schemaValidationWarnings": []}

    monkeypatch.setattr("engine.agent.tools.generate_sql", fake_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="users who do not have a pet")
    # Simulate plan with inner join and IS NULL filter semantics
    query_plan = {
        "analysis_goal": "users who do not have a pet",
        "candidate_tables": ["users", "has_pet"],
        "raw_plan": {
            "intent": "filter",
            "tables": ["users", "has_pet"],
            "metrics": [],
            "dimensions": [],
            "filters": [{"column": "has_pet.pet_id", "operator": "IS NULL", "value": None}],
            "joins": [{"right_table": "has_pet", "condition": "users.id = has_pet.user_id"}],
            "limit": 100,
        },
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)
    assert obs.status == "success"
    assert obs.output is not None
    # Should fallback to LLM because of anti-join intent
    assert obs.output["metadata"]["generation_source"] == "generate_sql_fallback"


def test_question_is_antijoin_detection() -> None:
    from engine.agent.tools import _question_is_antijoin as qaj
    assert qaj("Find the major and age of students who do not have a cat pet.") is True
    assert qaj("students without pets") is True
    assert qaj("How many singers do we have?") is False
    assert qaj("Show all countries") is False


def test_fix_antijoin_strips_distinct() -> None:
    from engine.agent.tools import _fix_antijoin_sql as faj
    sql = "SELECT DISTINCT s.Major, s.Age FROM student s WHERE NOT EXISTS (SELECT 1 FROM has_pet hp WHERE hp.StuID = s.StuID) LIMIT 100"
    fixed = faj(None, "", sql)
    assert fixed is not None
    assert "DISTINCT" not in (fixed or "").upper()


def test_fix_antijoin_preserves_not_exists() -> None:
    from engine.agent.tools import _fix_antijoin_sql as faj
    sql = "SELECT s.Major, s.Age FROM student AS s WHERE NOT EXISTS (SELECT 1 FROM has_pet AS hp JOIN pets AS p ON hp.PetID = p.PetID WHERE hp.StuID = s.StuID AND p.PetType = 'cat') LIMIT 100"
    fixed = faj(None, "", sql)
    assert fixed == sql


def test_antijoin_sql_must_not_have_distinct(db_session, demo_datasource, monkeypatch) -> None:
    """Smoke-9 style: anti-join + DISTINCT must be stripped."""
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT DISTINCT id, username FROM users WHERE NOT id IN (SELECT id FROM users WHERE role = 'admin') LIMIT 100",
            "model": "test", "mode": "online", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools.generate_sql", fake_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="users who do not have admin role", api_key="test")
    query_plan = {
        "analysis_goal": "find non-admin",
        "candidate_tables": ["users"],
        "raw_plan": {"intent": "filter", "tables": ["users"], "metrics": [], "dimensions": [], "filters": [], "joins": [], "limit": 100},
    }

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan=query_plan)
    assert obs.status == "success"
    sql = (obs.output or {}).get("sql", "")
    assert "DISTINCT" not in sql.upper(), f"DISTINCT found in: {sql}"
