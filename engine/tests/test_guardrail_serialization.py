import json
from typing import Any

from fastapi.testclient import TestClient
from sqlglot import exp

from engine.main import LOCAL_SECURE_TOKEN, app
import engine.sql.guardrail as guardrail_module
from engine.sql.trust_gate import TrustGate


class _DummyQuery:
    def filter(self, *_args: Any, **_kwargs: Any) -> "_DummyQuery":
        return self

    def first(self) -> None:
        return None


class _DummyDb:
    def query(self, *_args: Any, **_kwargs: Any) -> _DummyQuery:
        return _DummyQuery()


def test_query_validate_response_is_json_serializable_without_internal_ast() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/query/validate",
        json={"sql": "SELECT 1"},
        headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "_parsed_ast" not in payload
    json.dumps(payload)


def test_guardrail_check_result_is_json_serializable_without_internal_ast() -> None:
    result = guardrail_module.guardrail_check("SELECT 1")

    assert "_parsed_ast" not in result
    json.dumps(result)


def test_guardrail_check_with_ast_returns_ast_out_of_band() -> None:
    assert hasattr(guardrail_module, "guardrail_check_with_ast")

    result, parsed_ast = guardrail_module.guardrail_check_with_ast("SELECT 1")

    assert "_parsed_ast" not in result
    assert isinstance(parsed_ast, exp.Expression)
    json.dumps(result)


def test_trust_gate_public_result_does_not_expose_internal_ast() -> None:
    trust_gate = TrustGate(
        _DummyDb(),  # type: ignore[arg-type]
        lambda _sql_or_ast, _db, _datasource_id: [],
    )

    result = trust_gate.evaluate("missing-ds", "SELECT 1")

    assert "_parsed_ast" not in result["guardrail"]
    json.dumps(result)
