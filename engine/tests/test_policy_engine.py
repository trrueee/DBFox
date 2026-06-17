from __future__ import annotations

import sqlglot

from engine.errors import DBFoxError
from engine.models import DataSource
from engine.policy.engine import PolicyEngine


def test_query_policy_blocks_when_sql_cannot_be_parsed(monkeypatch) -> None:
    ds = DataSource(
        id="ds-policy",
        name="readonly",
        host="localhost",
        port=0,
        database_name="/tmp/test-policy.db",
        username="test",
        password_ciphertext="test",
        password_nonce="test",
        db_type="sqlite",
        status="active",
        is_read_only=True,
        env="prod",
    )

    def fail_parse(_sql: str):
        raise sqlglot.errors.ParseError("broken syntax")

    monkeypatch.setattr("engine.policy.engine.sqlglot.parse", fail_parse)

    try:
        PolicyEngine.enforce_query_policy(ds, "SELECT replace_count FROM grant_records")
    except DBFoxError as exc:
        assert exc.code == "POLICY_PARSE_ERROR"
    else:
        raise AssertionError("Unparseable SQL must be blocked by policy.")
