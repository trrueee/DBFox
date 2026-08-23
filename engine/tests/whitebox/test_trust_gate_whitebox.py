from dlcs.dbfox_data.backend.sql.safety_contracts import DatabaseSafetyScope
from dlcs.dbfox_data.backend.sql.trust_gate import TrustGate


def _scope(*, environment: str = "dev") -> DatabaseSafetyScope:
    return DatabaseSafetyScope(
        resource_id="ds-1",
        exists=True,
        dialect="sqlite",
        environment=environment,
    )


# covers: TG-1 guardrail reject
def test_tg1_reject():
    result = TrustGate(lambda _ast: []).evaluate(
        _scope(), "DROP TABLE t", policy="readonly"
    )
    assert result["riskLevel"] == "danger"
    assert result["canExecute"] is False


# covers: TG-2 schema warnings
def test_tg2_schema_warnings():
    result = TrustGate(lambda _ast: ["Table not found"]).evaluate(
        _scope(), "SELECT id FROM t", policy="readonly"
    )
    assert result["riskLevel"] == "warning"
    assert result["canExecute"] is True


# covers: TG-3 guardrail warning
def test_tg3_guardrail_warning():
    result = TrustGate(lambda _ast: []).evaluate(
        _scope(), "SELECT * FROM t LIMIT 1", policy="readonly"
    )
    assert result["riskLevel"] == "warning"


# covers: TG-4 all pass
def test_tg4_all_pass():
    result = TrustGate(lambda _ast: []).evaluate(
        _scope(), "SELECT id FROM t LIMIT 5", policy="readonly"
    )
    assert result["riskLevel"] == "safe"


# covers: TG-5 prod + agent_readonly
def test_tg5_prod_agent_readonly():
    result = TrustGate(lambda _ast: []).evaluate(
        _scope(environment="prod"),
        "SELECT id FROM t LIMIT 5",
        policy="agent_readonly",
    )
    assert result["requiresConfirmation"] is True


# covers: TG-6 dev + agent_readonly + warning
def test_tg6_dev_agent_readonly_warning():
    result = TrustGate(lambda _ast: ["Warning"]).evaluate(
        _scope(), "SELECT id FROM t LIMIT 5", policy="agent_readonly"
    )
    assert result["requiresConfirmation"] is True


# covers: TG-7 user_readonly any env
def test_tg7_user_readonly_any_env():
    result = TrustGate(lambda _ast: []).evaluate(
        _scope(environment="prod"),
        "SELECT id FROM t LIMIT 5",
        policy="user_readonly",
    )
    assert result["requiresConfirmation"] is False
