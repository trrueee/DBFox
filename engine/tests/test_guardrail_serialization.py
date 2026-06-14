import json
from typing import Any

from fastapi.testclient import TestClient

from engine.main import LOCAL_SECURE_TOKEN, app
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


def test_trust_gate_public_result_does_not_expose_internal_ast() -> None:
    trust_gate = TrustGate(
        _DummyDb(),  # type: ignore[arg-type]
        lambda _sql_or_ast, _db, _datasource_id: [],
    )

    result = trust_gate.evaluate("missing-ds", "SELECT 1")

    assert "_parsed_ast" not in result["guardrail"]
    json.dumps(result)
