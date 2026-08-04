from __future__ import annotations

import pytest

from engine.errors import GuardrailValidationError
from engine.sql.dialect_context import DialectContext
from engine.sql.dry_run import dry_run_query
from engine.sql.explain_validator import validate_explain_sql
from engine.sql.guardrail import guardrail_check
from engine.sql.readonly_query import (
    ReadonlyQueryError,
    parse_single_readonly_query,
)
from engine.sql.safety.service import SqlSafetyService
from engine.sql.sql_backed_view import (
    SqlBackedViewError,
    build_sql_backed_page_sql,
)


READONLY_POSTGRES_QUERIES = [
    "SELECT 1 AS value",
    "WITH values_cte AS (SELECT 1 AS value) SELECT value FROM values_cte",
    "SELECT 1 AS value UNION SELECT 2 AS value",
    "SELECT 1 AS value INTERSECT SELECT 1 AS value",
    "SELECT 1 AS value EXCEPT SELECT 2 AS value",
]


@pytest.mark.parametrize("sql", READONLY_POSTGRES_QUERIES)
def test_canonical_contract_accepts_readonly_query_shapes(sql: str) -> None:
    expression = parse_single_readonly_query(sql, "postgres")

    assert expression is not None
    validate_explain_sql(sql, "postgres")
    ctx = DialectContext(datasource_id="readonly-contract", dialect="postgresql")
    assert SqlSafetyService().validate_source_artifact_sql(sql, ctx) == []
    derived = build_sql_backed_page_sql(
        base_sql=sql,
        dialect="postgres",
        columns=["value"],
        limit=10,
    )
    assert derived.sql


@pytest.mark.parametrize(
    ("sql", "dialect"),
    [
        ("SELECT 1; SELECT 2", "postgres"),
        ("INSERT INTO events(id) VALUES (1)", "postgres"),
        ("UPDATE events SET id = 2", "postgres"),
        ("DELETE FROM events", "postgres"),
        ("CREATE TABLE events(id INTEGER)", "postgres"),
        (
            "WITH changed AS (DELETE FROM events RETURNING id) "
            "SELECT id FROM changed",
            "postgres",
        ),
        ("SELECT id FROM events FOR UPDATE", "postgres"),
        ("SELECT * FROM events INTO OUTFILE '/tmp/events.csv'", "mysql"),
        ("SELECT nextval('events_id_seq')", "postgres"),
        ("SELECT setval('events_id_seq', 10)", "postgres"),
        ("SELECT pg_advisory_lock(42)", "postgres"),
        ("SELECT GET_LOCK('dbfox', 1)", "mysql"),
        ("SELECT RELEASE_LOCK('dbfox')", "mysql"),
    ],
)
def test_canonical_contract_rejects_writes_locks_and_stateful_functions(
    sql: str,
    dialect: str,
) -> None:
    with pytest.raises(ReadonlyQueryError):
        parse_single_readonly_query(sql, dialect)

    with pytest.raises(GuardrailValidationError):
        validate_explain_sql(sql, dialect)

    with pytest.raises(SqlBackedViewError):
        build_sql_backed_page_sql(
            base_sql=sql,
            dialect=dialect,
            columns=["id"],
        )

    ctx = DialectContext(
        datasource_id="readonly-contract",
        dialect="postgresql" if dialect == "postgres" else "mysql",
    )
    assert SqlSafetyService().validate_source_artifact_sql(sql, ctx)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 AS value",
        "WITH values_cte AS (SELECT 1 AS value) SELECT value FROM values_cte",
        "SELECT 1 AS value UNION SELECT 2 AS value",
        "SELECT 1 AS value INTERSECT SELECT 1 AS value",
        "SELECT 1 AS value EXCEPT SELECT 2 AS value",
    ],
)
def test_sqlite_dry_run_accepts_canonical_readonly_shapes(
    db_session,
    test_datasource,
    sql: str,
) -> None:
    result = dry_run_query(db_session, test_datasource.id, sql)

    assert result.ok is True
    assert result.blocked_reason is None


@pytest.mark.parametrize(
    ("sql", "expected_rule"),
    [
        ("SELECT nextval('events_id_seq')", "dangerous_function"),
        ("SELECT pg_advisory_lock(42)", "dangerous_function"),
        ("SELECT GET_LOCK('dbfox', 1)", "dangerous_function"),
    ],
)
def test_guardrail_reports_stateful_query_functions(
    sql: str,
    expected_rule: str,
) -> None:
    dialect = "mysql" if "GET_LOCK" in sql else "postgres"
    result = guardrail_check(sql, dialect=dialect)

    assert result["result"] == "reject"
    assert any(check["rule"] == expected_rule for check in result["checks"])
