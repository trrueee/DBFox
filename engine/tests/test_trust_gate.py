from engine.sql.executor import validate_sql_schema
from engine.schema_sync import sync_schema
from engine.sql.dry_run import DryRunResult
from engine.sql.trust_gate import TrustGate


def test_trust_gate_safe_select(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)

    result = TrustGate(db_session, validate_sql_schema).evaluate(
        test_datasource.id,
        "SELECT id, username FROM users LIMIT 10",
    )

    assert result["riskLevel"] == "safe"
    assert result["requiresConfirmation"] is False
    assert result["canExecute"] is True
    assert result["schemaWarnings"] == []
    assert result["guardrail"]["result"] == "pass"


def test_trust_gate_allows_order_by_projection_alias(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)

    result = TrustGate(db_session, validate_sql_schema).evaluate(
        test_datasource.id,
        """
        SELECT username, COUNT(*) AS invocation_count
        FROM users
        GROUP BY username
        ORDER BY invocation_count DESC
        LIMIT 10
        """,
        policy="agent_readonly",
    )

    assert result["schemaWarnings"] == []
    assert result["riskLevel"] == "safe"


def test_trust_gate_schema_warning_requires_confirmation(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)

    result = TrustGate(db_session, validate_sql_schema).evaluate(
        test_datasource.id,
        "SELECT imaginary_column FROM users LIMIT 10",
        policy="agent_readonly",
    )

    assert result["riskLevel"] == "warning"
    assert result["requiresConfirmation"] is True
    assert result["canExecute"] is True
    assert any("imaginary_column" in warning for warning in result["schemaWarnings"])


def test_trust_gate_rejects_dangerous_sql(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)

    result = TrustGate(db_session, validate_sql_schema).evaluate(
        test_datasource.id,
        "DROP TABLE users",
    )

    assert result["riskLevel"] == "danger"
    assert result["requiresConfirmation"] is False
    assert result["canExecute"] is False
    assert result["guardrail"]["result"] == "reject"


def test_trust_gate_prod_datasource_requires_confirmation(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    test_datasource.env = "prod"
    db_session.commit()

    result = TrustGate(db_session, validate_sql_schema).evaluate(
        test_datasource.id,
        "SELECT id, username FROM users LIMIT 10",
        policy="agent_readonly",
    )

    assert result["riskLevel"] == "safe"
    assert result["requiresConfirmation"] is True
    assert result["canExecute"] is True
    assert any("Production datasource" in message for message in result["messages"])


def test_trust_gate_execution_decision_blocks_invalid_order_by_syntax(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)

    decision = TrustGate(db_session, validate_sql_schema).execution_decision(
        test_datasource.id,
        "SELECT id FROM users ORDER BY ARRAY() LIMIT 10",
        policy="agent_readonly",
    )

    assert decision.can_execute is False
    assert decision.passed is False
    assert decision.safe_sql is None
    assert "guardrail_reject" in decision.blocked_reasons


def test_trust_gate_execution_decision_blocks_missing_table_schema_error(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)

    decision = TrustGate(db_session, validate_sql_schema).execution_decision(
        test_datasource.id,
        "SELECT id FROM missing_table LIMIT 10",
        policy="agent_readonly",
    )

    assert decision.can_execute is False
    assert decision.passed is False
    assert decision.safe_sql is None
    assert "schema_error" in decision.blocked_reasons


def test_trust_gate_execution_decision_blocks_when_dry_run_unavailable(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    sync_schema(db_session, test_datasource.id)

    def fail_dry_run(*_args, **_kwargs):
        raise RuntimeError("dry run connection unavailable")

    monkeypatch.setattr("engine.sql.trust_gate.dry_run_query", fail_dry_run)

    decision = TrustGate(db_session, validate_sql_schema).execution_decision(
        test_datasource.id,
        "SELECT id FROM users LIMIT 10",
        policy="agent_readonly",
    )

    assert decision.can_execute is False
    assert decision.passed is False
    assert decision.safe_sql is None
    assert "explain_unavailable" in decision.blocked_reasons
    assert any("dry run connection unavailable" in message for message in decision.messages)


def test_trust_gate_execution_decision_dry_runs_guardrail_safe_sql(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    sync_schema(db_session, test_datasource.id)
    original_sql = "SELECT id FROM users"
    safe_sql = "SELECT id FROM users LIMIT 1000"
    dry_run_sql: list[str] = []

    def fake_guardrail(sql: str, dialect: str = "mysql"):
        return {
            "result": "pass",
            "originalSql": sql,
            "safeSql": safe_sql,
            "checks": [],
            "message": "ok",
        }

    def fake_dry_run(_db, _datasource_id: str, sql: str) -> DryRunResult:
        dry_run_sql.append(sql)
        return DryRunResult(True)

    monkeypatch.setattr("engine.sql.trust_gate.guardrail_check", fake_guardrail)
    monkeypatch.setattr("engine.sql.trust_gate.dry_run_query", fake_dry_run)

    decision = TrustGate(db_session, validate_sql_schema).execution_decision(
        test_datasource.id,
        original_sql,
        policy="agent_readonly",
    )

    assert dry_run_sql == [safe_sql]
    assert decision.original_sql == original_sql
    assert decision.safe_sql == safe_sql
    assert decision.can_execute is True
    assert any("safe_sql" in message for message in decision.messages)


def test_trust_gate_execution_decision_original_sql_does_not_drive_dry_run_result(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    sync_schema(db_session, test_datasource.id)
    safe_sql = "SELECT id FROM users LIMIT 1000"

    def fake_guardrail(sql: str, dialect: str = "mysql"):
        return {
            "result": "pass",
            "originalSql": sql,
            "safeSql": safe_sql,
            "checks": [],
            "message": "ok",
        }

    def fake_dry_run(_db, _datasource_id: str, sql: str) -> DryRunResult:
        if sql != safe_sql:
            return DryRunResult(False, "syntax_error", "original SQL should not be dry-run")
        return DryRunResult(True)

    monkeypatch.setattr("engine.sql.trust_gate.guardrail_check", fake_guardrail)
    monkeypatch.setattr("engine.sql.trust_gate.dry_run_query", fake_dry_run)

    decision = TrustGate(db_session, validate_sql_schema).execution_decision(
        test_datasource.id,
        "SELECT id FROM users",
        policy="agent_readonly",
    )

    assert decision.can_execute is True
    assert decision.safe_sql == safe_sql
    assert "syntax_error" not in decision.blocked_reasons


def test_trust_gate_execution_decision_blocks_when_safe_sql_dry_run_fails(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    sync_schema(db_session, test_datasource.id)
    safe_sql = "SELECT missing_column FROM users LIMIT 1000"
    dry_run_sql: list[str] = []

    def fake_guardrail(sql: str, dialect: str = "mysql"):
        return {
            "result": "pass",
            "originalSql": sql,
            "safeSql": safe_sql,
            "checks": [],
            "message": "ok",
        }

    def fake_dry_run(_db, _datasource_id: str, sql: str) -> DryRunResult:
        dry_run_sql.append(sql)
        if sql == safe_sql:
            return DryRunResult(False, "schema_error", "no such column: missing_column")
        return DryRunResult(True)

    monkeypatch.setattr("engine.sql.trust_gate.guardrail_check", fake_guardrail)
    monkeypatch.setattr("engine.sql.trust_gate.dry_run_query", fake_dry_run)

    decision = TrustGate(db_session, validate_sql_schema).execution_decision(
        test_datasource.id,
        "SELECT id FROM users",
        policy="agent_readonly",
    )

    assert dry_run_sql == [safe_sql]
    assert decision.can_execute is False
    assert decision.safe_sql is None
    assert "schema_error" in decision.blocked_reasons


def test_trust_gate_execution_decision_skips_dry_run_when_guardrail_rejects(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    sync_schema(db_session, test_datasource.id)
    dry_run_sql: list[str] = []

    def fake_guardrail(sql: str, dialect: str = "mysql"):
        return {
            "result": "reject",
            "originalSql": sql,
            "safeSql": "",
            "checks": [{"rule": "select_only", "level": "reject", "message": "blocked"}],
            "message": "blocked",
        }

    def fake_dry_run(_db, _datasource_id: str, sql: str) -> DryRunResult:
        dry_run_sql.append(sql)
        return DryRunResult(True)

    monkeypatch.setattr("engine.sql.trust_gate.guardrail_check", fake_guardrail)
    monkeypatch.setattr("engine.sql.trust_gate.dry_run_query", fake_dry_run)

    decision = TrustGate(db_session, validate_sql_schema).execution_decision(
        test_datasource.id,
        "SELECT id FROM users",
        policy="agent_readonly",
    )

    assert dry_run_sql == []
    assert decision.can_execute is False
    assert decision.safe_sql is None
    assert "guardrail_reject" in decision.blocked_reasons


def test_trust_gate_execution_decision_skips_dry_run_when_safe_sql_is_empty(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    sync_schema(db_session, test_datasource.id)
    dry_run_sql: list[str] = []

    def fake_guardrail(sql: str, dialect: str = "mysql"):
        return {
            "result": "pass",
            "originalSql": sql,
            "safeSql": "",
            "checks": [],
            "message": "ok",
        }

    def fake_dry_run(_db, _datasource_id: str, sql: str) -> DryRunResult:
        dry_run_sql.append(sql)
        return DryRunResult(True)

    monkeypatch.setattr("engine.sql.trust_gate.guardrail_check", fake_guardrail)
    monkeypatch.setattr("engine.sql.trust_gate.dry_run_query", fake_dry_run)

    decision = TrustGate(db_session, validate_sql_schema).execution_decision(
        test_datasource.id,
        "SELECT id FROM users",
        policy="agent_readonly",
    )

    assert dry_run_sql == []
    assert decision.can_execute is False
    assert decision.safe_sql is None
    assert "safe_sql_missing" in decision.blocked_reasons
