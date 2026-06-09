from __future__ import annotations

import uuid

import pytest

from engine.agent import AgentRunRequest
from engine.agent.semantic_retry_policy import semantic_retry_prompt
from engine.agent.tools import (
    _prepare_generated_sql,
    _render_sql_from_query_plan,
    build_query_plan_tool,
    generate_sql_tool,
    revise_sql_tool,
    suggest_chart_tool,
    validate_sql_tool,
)
from engine.agent.semantic_contract import build_query_contract
from engine.agent.sql_semantic_verifier import SemanticViolation
from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.schema_sync import sync_schema


def test_build_query_plan_tool_for_chinese_question(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="统计每天订单量")

    obs = build_query_plan_tool(db_session, req, {"schema_context": "", "selected_tables": ["orders"]})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["analysis_goal"]
    assert "orders" in obs.output["candidate_tables"]


def test_generate_sql_tool_returns_raw_select_star_without_rewrite(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql_from_schema_context(**_kwargs):
        return {
            "sql": "SELECT * FROM users",
            "model": "test",
            "mode": "schema_direct",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
            "metadata": {
                "generation_source": "schema_direct_llm",
                "dialect": "mysql",
                "used_query_plan": False,
                "used_renderer": False,
                "used_demo_fallback": False,
            },
        }

    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql_from_schema_context)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="查询所有用户", api_key="sk-test")

    obs = generate_sql_tool(db_session, req)

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["sql"] == "SELECT * FROM users"
    assert obs.output["rewrite_notes"] == []
    assert obs.output["metadata"]["used_guardrail_in_generate"] is False
    assert obs.output["metadata"]["used_semantic_retry"] is False


def test_generate_sql_tool_default_path_does_not_call_prepare_guardrail_renderer_legacy_or_retry_prompt(
    db_session, demo_datasource, monkeypatch
) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fail_prepare(*_args, **_kwargs):
        raise AssertionError("_prepare_generated_sql must not run in sql.generate")

    def fail_guardrail(*_args, **_kwargs):
        raise AssertionError("guardrail_check must not run in sql.generate")

    def fail_renderer(*_args, **_kwargs):
        raise AssertionError("_render_sql_from_query_plan must not run in sql.generate")

    def fail_legacy(*_args, **_kwargs):
        raise AssertionError("legacy generate_sql must not run in sql.generate")

    def fail_retry_prompt(*_args, **_kwargs):
        raise AssertionError("semantic_retry_prompt must not run in default sql.generate")

    def fake_schema_direct(**_kwargs):
        return {
            "sql": "SELECT COUNT(*) FROM users",
            "model": "test",
            "mode": "schema_direct",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
            "metadata": {"generation_source": "schema_direct_llm"},
        }

    monkeypatch.setattr("engine.agent.tools._prepare_generated_sql", fail_prepare)
    monkeypatch.setattr("engine.agent.tools.guardrail_check", fail_guardrail)
    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", fail_renderer)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_schema_direct)
    monkeypatch.setattr("engine.agent.tools.semantic_retry_prompt", fail_retry_prompt)
    monkeypatch.setattr("engine.ai.generate_sql", fail_legacy)

    req = AgentRunRequest(datasource_id=demo_datasource.id, question="count users", api_key="sk-test")
    obs = generate_sql_tool(db_session, req, schema_context={"schema_context": "TABLE users(id)"})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["metadata"]["generation_source"] == "schema_direct_llm"
    assert obs.output["metadata"]["used_guardrail_in_generate"] is False
    assert obs.output["metadata"]["used_semantic_retry"] is False


def test_generate_sql_tool_schema_direct_does_not_call_renderer_or_legacy_generate_sql(
    db_session, demo_datasource, monkeypatch
) -> None:
    sync_schema(db_session, demo_datasource.id)
    calls: list[dict[str, object]] = []

    def fail_renderer(*_args, **_kwargs):
        raise AssertionError("renderer should not run in default schema_direct path")

    def fake_schema_direct(**kwargs):
        calls.append(kwargs)
        return {
            "sql": "SELECT COUNT(*) AS total_users FROM users",
            "model": "test",
            "mode": "schema_direct",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
            "metadata": {
                "generation_source": "schema_direct_llm",
                "dialect": kwargs["dialect"],
                "used_query_plan": False,
                "used_renderer": False,
                "used_demo_fallback": False,
            },
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", fail_renderer)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_schema_direct)
    monkeypatch.setattr(
        "engine.agent.tools.QueryPlanBuilder.build",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("QueryPlanBuilder should not run in sql.generate")),
    )
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="count users", api_key="sk-test")
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
    assert calls and calls[0]["question"] == "count users"
    assert obs.output["metadata"]["generation_source"] == "schema_direct_llm"
    assert obs.output["metadata"]["used_renderer"] is False
    assert obs.output["metadata"]["used_query_plan_as_prompt"] is False
    assert obs.output["metadata"]["used_demo_fallback"] is False
    assert "COUNT(*) AS total_users" in obs.output["sql"]
    assert "FROM users" in obs.output["sql"]


def test_generate_sql_tool_non_demo_without_api_key_fails_closed(db_session) -> None:
    ds = DataSource(
        id=str(uuid.uuid4()),
        name="sqlite_real",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name="/tmp/real.sqlite",
        username="",
        password_ciphertext="",
        password_nonce="",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    req = AgentRunRequest(datasource_id=ds.id, question="list products")
    obs = generate_sql_tool(db_session, req, schema_context={"schema_context": "TABLE students(id, name)"})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["sql"] is None
    assert obs.output["error"] == "LLM API key required for non-demo Text-to-SQL generation"
    assert obs.output["metadata"]["used_demo_fallback"] is False


def test_generate_sql_tool_records_semantic_contract_violations(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT Airline FROM flights GROUP BY Airline",
            "model": "test",
            "mode": "online",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", lambda **_kwargs: fake_generate_sql())
    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="Which airlines have at least 10 flights?",
        api_key="test",
        semantic_mode="retry",
    )

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan={})

    assert obs.status == "success"
    assert obs.output is not None
    metadata = obs.output["metadata"]
    assert metadata["semantic_contract"]["aggregation"]["type"] == "count_threshold"
    assert {item["code"] for item in metadata["semantic_violations"]} == {"having_missing"}
    assert metadata["semantic_retry_attempted"] is True
    assert metadata["semantic_mode"] == "retry"
    assert "HAVING" not in obs.output["sql"].upper()


def test_generate_sql_tool_retries_once_with_contract_violations(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)
    prompts: list[str] = []

    def fake_generate_sql_from_schema_context(**kwargs):
        prompts.append(str(kwargs["question"]))
        if len(prompts) == 1:
            return {
                "sql": "SELECT Airline FROM flights GROUP BY Airline",
                "model": "test",
                "mode": "schema_direct",
                "latencyMs": 1,
                "schemaValidationWarnings": [],
                "metadata": {"generation_source": "schema_direct_llm", "used_renderer": False, "used_demo_fallback": False},
            }
        return {
            "sql": "SELECT Airline FROM flights GROUP BY Airline HAVING COUNT(*) >= 10",
            "model": "test",
            "mode": "schema_direct",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
            "metadata": {"generation_source": "schema_direct_llm", "used_renderer": False, "used_demo_fallback": False},
        }

    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql_from_schema_context)
    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="Which airlines have at least 10 flights?",
        api_key="test",
        semantic_mode="retry",
    )

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context": "schema", "schema_context_size": 1}, query_plan={})

    assert obs.status == "success"
    assert obs.output is not None
    assert len(prompts) == 2
    assert "SQL_CONTRACT" in prompts[1]
    assert "having_missing" in prompts[1]
    assert "HAVING COUNT(*) >= 10" in obs.output["sql"]
    assert obs.output["metadata"]["semantic_retry_attempted"] is True
    assert obs.output["metadata"]["semantic_retry_accepted"] is True
    assert len(obs.output["metadata"]["semantic_violations"]) == 0


def test_semantic_retry_prompt_includes_code_specific_guidance() -> None:
    contract = build_query_contract(
        "What are all distinct countries where singers above age 20 are from?",
        {},
        {},
    )

    prompt = semantic_retry_prompt(
        question="What are all distinct countries where singers above age 20 are from?",
        schema_context={},
        contract=contract,
        previous_sql="SELECT Country FROM singer WHERE Age > 20",
        violations=[
            SemanticViolation(
                code="distinct_missing",
                severity="retryable",
                message="DISTINCT is required.",
            )
        ],
    )

    assert "Use SELECT DISTINCT" in prompt


def test_render_sql_from_query_plan_omits_empty_raw_plan_order_by(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
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

    sql = _render_sql_from_query_plan(db_session, demo_datasource.id, query_plan)

    assert sql is not None
    assert "ORDER BY" not in sql.upper()


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


def test_generate_sql_tool_demo_without_api_key_fails_closed(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list products", api_key=None)

    obs = generate_sql_tool(db_session, req)

    assert obs.status == "success"
    assert obs.input is not None
    assert obs.input["has_api_key"] is False
    assert obs.output is not None
    assert obs.output["sql"] is None
    assert obs.output["error"] == "LLM API key required for non-demo Text-to-SQL generation"
    assert obs.output["metadata"]["used_demo_fallback"] is False


def test_validate_sql_tool_rewrites_select_star_with_truncation_limit(db_session, demo_datasource) -> None:
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

    obs = validate_sql_tool(db_session, demo_datasource.id, "SELECT * FROM wide_table")

    assert obs.status == "success"
    assert obs.output is not None
    rewrite = obs.output["rewrite"]
    assert rewrite["select_star_column_limit"] == 12
    assert rewrite["truncated_tables"] == ["wide_table"]
    assert "first 12 columns" in rewrite["message"]
    assert "select_star_rewritten_to_explicit_columns" in obs.output["rewrite_notes"]
    prepared_sql = obs.output["prepared_sql"]
    assert prepared_sql is not None
    assert "col_13" not in prepared_sql
    assert obs.output["guardrail"]["result"] in {"pass", "warn", "reject"}


@pytest.mark.parametrize("sql", ["DELETE FROM users", "UPDATE users SET role = 'admin'", "DROP TABLE users"])
def test_validate_sql_tool_blocks_write_operations(db_session, demo_datasource, sql: str) -> None:
    sync_schema(db_session, demo_datasource.id)

    obs = validate_sql_tool(db_session, demo_datasource.id, sql)

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["can_execute"] is False
    assert obs.output["guardrail"]["result"] == "reject"


def test_validate_sql_tool_rewrites_select_star_and_produces_safe_sql(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)

    obs = validate_sql_tool(db_session, demo_datasource.id, "SELECT * FROM users")

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["can_execute"] is True
    assert obs.output["safe_sql"] is not None
    assert "SELECT *" not in obs.output["safe_sql"].upper()
    assert "users.id" in obs.output["safe_sql"]
    assert "select_star_rewritten_to_explicit_columns" in obs.output["rewrite_notes"]
    assert obs.output["guardrail"]["result"] in {"pass", "warn"}


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


def test_render_structured_order_by_list_and_dict(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    metric = {"name": "total_users", "expression": "COUNT(*)"}
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

    sql = _render_sql_from_query_plan(db_session, demo_datasource.id, query_plan)
    assert sql is not None
    assert "ORDER BY" in sql.upper()
    assert "DESC" in sql.upper()
    query_plan["raw_plan"]["order_by"] = [{"column": "id", "direction": "DESC"}, {"column": "username", "direction": "ASC"}]
    sql2 = _render_sql_from_query_plan(db_session, demo_datasource.id, query_plan)
    assert sql2 is not None
    assert "ORDER BY" in sql2.upper()
    assert "username ASC" in sql2 or "USERNAME ASC" in sql2.upper()


def test_order_by_illegal_direction_omits_order_by(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
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

    sql = _render_sql_from_query_plan(db_session, demo_datasource.id, query_plan)
    assert sql is not None
    assert "ORDER BY" not in sql.upper()


def test_render_stringified_python_repr_order_by(db_session, demo_datasource) -> None:
    """Stringified Python repr like \"[{'column': 'id', 'direction': 'DESC'}]\" must be parsed and rendered."""
    sync_schema(db_session, demo_datasource.id)
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

    sql = _render_sql_from_query_plan(db_session, demo_datasource.id, query_plan)
    assert sql is not None
    assert "ORDER BY id DESC" in sql or "ORDER BY ID DESC" in sql.upper()


def test_render_json_string_order_by(db_session, demo_datasource) -> None:
    """JSON string like '[{\"column\":\"id\",\"direction\":\"DESC\"}]' must be parsed and rendered."""
    sync_schema(db_session, demo_datasource.id)
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

    sql = _render_sql_from_query_plan(db_session, demo_datasource.id, query_plan)
    assert sql is not None
    assert "ORDER BY id DESC" in sql or "ORDER BY ID DESC" in sql.upper()


def test_render_stringified_repr_illegal_direction_omits_order_by(db_session, demo_datasource) -> None:
    """Stringified repr with illegal direction (DOWN) should silently omit ORDER BY."""
    sync_schema(db_session, demo_datasource.id)
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

    sql = _render_sql_from_query_plan(db_session, demo_datasource.id, query_plan)
    assert sql is not None
    assert "ORDER BY" not in sql.upper()


def test_smoke2_ordered_by_age_desc_must_have_order_by(db_session, demo_datasource) -> None:
    """Experimental renderer: ordered by age from oldest to youngest → ORDER BY Age DESC."""
    sync_schema(db_session, demo_datasource.id)
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

    sql = _render_sql_from_query_plan(db_session, demo_datasource.id, query_plan)
    assert sql is not None
    sql_upper = sql.upper()
    assert "ORDER BY" in sql_upper
    assert "DESC" in sql_upper
    assert "username" in sql.lower() or "USERNAME" in sql_upper

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

    sql = _render_sql_from_query_plan(db_session, demo_datasource.id, query_plan)
    assert sql is not None
    assert "IS NULL" in sql
    assert "'None'" not in sql and "\"None\"" not in sql


def test_plan_requires_llm_for_antijoin_and_inner_join(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
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

    sql = _render_sql_from_query_plan(db_session, demo_datasource.id, query_plan)
    assert sql is None


def test_antijoin_sql_records_semantic_violation_without_rewriting(db_session, demo_datasource, monkeypatch) -> None:
    """Semantic verifier reports anti-join shape issues without hard-rewriting SQL."""
    sync_schema(db_session, demo_datasource.id)

    def fake_schema_direct(**_kwargs):
        return {
            "sql": "SELECT DISTINCT users.id FROM users JOIN has_pet ON users.id = has_pet.user_id LIMIT 100",
            "model": "test",
            "mode": "schema_direct",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
            "metadata": {"generation_source": "schema_direct_llm"},
        }

    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_schema_direct)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="users who do not have pets", api_key="test")

    obs = generate_sql_tool(db_session, req, schema_context={"schema_context_size": 1}, query_plan={})
    assert obs.status == "success"
    sql = (obs.output or {}).get("sql", "")
    assert "DISTINCT" in sql.upper()
    metadata = (obs.output or {}).get("metadata", {})
    assert metadata["used_guardrail_in_generate"] is False
    assert {item["code"] for item in metadata.get("semantic_violations", [])} == {"antijoin_outer_join"}


# ============================================================
# Projection-only retry validation
# ============================================================

from engine.agent.semantic_contract import QueryContract, DistinctContract
from engine.sql.compiler import SQLProjectionConstraintVerifier


def _make_contract() -> QueryContract:
    return QueryContract(confidence=0.75)


def _validate_projection_retry(original_sql: str, retry_sql: str, contract: QueryContract) -> bool:
    return SQLProjectionConstraintVerifier().validate_retry(original_sql, retry_sql, contract)


def test_projection_retry_accept_select_only_change() -> None:
    """SELECT list only changed → accept."""
    original = "SELECT student.StuID, student.LName, student.Fname, student.Age FROM student JOIN has_pet ON student.StuID = has_pet.StuID WHERE student.LName = 'Smith' LIMIT 100"
    retry_sql = "SELECT has_pet.PetID FROM student JOIN has_pet ON student.StuID = has_pet.StuID WHERE student.LName = 'Smith' LIMIT 100"
    assert _validate_projection_retry(original, retry_sql, _make_contract()) is True


def test_projection_retry_reject_where_changed() -> None:
    """WHERE changed → reject."""
    original = "SELECT student.StuID, student.LName FROM student WHERE student.LName = 'Smith' LIMIT 100"
    retry_sql = "SELECT student.StuID FROM student WHERE student.LName = 'Jones' LIMIT 100"
    assert _validate_projection_retry(original, retry_sql, _make_contract()) is False


def test_projection_retry_reject_join_removed() -> None:
    """JOIN removed → reject."""
    original = "SELECT student.Fname FROM student JOIN has_pet ON student.StuID = has_pet.StuID LIMIT 100"
    retry_sql = "SELECT student.Fname FROM student LIMIT 100"
    assert _validate_projection_retry(original, retry_sql, _make_contract()) is False


def test_projection_retry_reject_order_by_changed() -> None:
    """ORDER BY changed → reject."""
    original = "SELECT Name FROM singer ORDER BY Age DESC LIMIT 10"
    retry_sql = "SELECT Name FROM singer ORDER BY Age ASC LIMIT 10"
    assert _validate_projection_retry(original, retry_sql, _make_contract()) is False


def test_projection_retry_reject_limit_changed() -> None:
    """LIMIT changed → reject."""
    original = "SELECT Name FROM singer LIMIT 100"
    retry_sql = "SELECT Name FROM singer LIMIT 10"
    assert _validate_projection_retry(original, retry_sql, _make_contract()) is False


def test_projection_retry_reject_distinct_dropped() -> None:
    """DISTINCT dropped when contract requires it → reject."""
    contract = _make_contract()
    contract.distinct = DistinctContract(required=True, reason="explicit_distinct")
    original = "SELECT DISTINCT student.Fname FROM student JOIN has_pet ON student.StuID = has_pet.StuID LIMIT 100"
    retry_sql = "SELECT student.Fname FROM student JOIN has_pet ON student.StuID = has_pet.StuID LIMIT 100"
    assert _validate_projection_retry(original, retry_sql, contract) is False


def test_projection_retry_accept_distinct_preserved() -> None:
    """DISTINCT preserved when required → accept."""
    contract = _make_contract()
    contract.distinct = DistinctContract(required=True, reason="explicit_distinct")
    original = "SELECT DISTINCT student.Fname, student.Age FROM student JOIN has_pet ON student.StuID = has_pet.StuID LIMIT 100"
    retry_sql = "SELECT DISTINCT student.Fname FROM student JOIN has_pet ON student.StuID = has_pet.StuID LIMIT 100"
    assert _validate_projection_retry(original, retry_sql, contract) is True


def test_projection_retry_accept_no_distinct_required() -> None:
    """DISTINCT not required in contract → select-only change accepted."""
    original = "SELECT student.Fname, student.Age FROM student JOIN has_pet ON student.StuID = has_pet.StuID LIMIT 100"
    retry_sql = "SELECT DISTINCT student.Fname FROM student JOIN has_pet ON student.StuID = has_pet.StuID LIMIT 100"
    assert _validate_projection_retry(original, retry_sql, _make_contract()) is True


def test_projection_retry_reject_group_by_changed() -> None:
    """GROUP BY changed → reject."""
    original = "SELECT PetType, AVG(pet_age) FROM pets GROUP BY PetType LIMIT 100"
    retry_sql = "SELECT PetType, AVG(pet_age) FROM pets GROUP BY PetType, pet_age LIMIT 100"
    assert _validate_projection_retry(original, retry_sql, _make_contract()) is False
