import pytest
import re
from pathlib import Path
from fastapi.testclient import TestClient
from engine.main import app, LOCAL_SECURE_TOKEN
from engine.models import DataSource
from engine.crypto import encrypt_password
from engine.sql.trust_gate import TrustGate
from engine.sql.safety_gate import validate_sql_schema

def parse_types_ts_interface(interface_name: str) -> set[str]:
    path = Path(__file__).resolve().parents[2] / "desktop" / "src" / "lib" / "api" / "types.ts"
    content = path.read_text(encoding="utf-8")
    pattern = rf"export\s+interface\s+{interface_name}\s*\{{([^}}]*)\}}"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        raise ValueError(f"Interface {interface_name} not found in types.ts")
    block = match.group(1)
    fields = set()
    for line in block.splitlines():
        # Only match direct fields indented with exactly 2 spaces
        field_match = re.match(r"^ {2}([a-zA-Z0-9_]+)\s*\??\s*:", line)
        if field_match:
            fields.add(field_match.group(1))
    return fields

@pytest.fixture
def client(db_session):
    from engine.db import get_db
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

def test_datasource_response_shape_matches_types_ts(client, db_session):
    cipher, nonce = encrypt_password("test")
    ds = DataSource(
        id="ds-test-contract",
        project_id="default",
        name="test_contract",
        host="localhost",
        port=3306,
        database_name="test",
        username="test",
        password_ciphertext=cipher,
        password_nonce=nonce,
        status="active"
    )
    db_session.add(ds)
    db_session.commit()

    resp = client.get("/api/v1/datasources", headers={"X-Local-Token": LOCAL_SECURE_TOKEN})
    assert resp.status_code == 200, resp.json()
    datasources = resp.json()
    assert len(datasources) > 0
    sample = datasources[0]

    # Verify essential fields defined in DataSource interface
    required_keys = {
        "id", "name", "host", "port", "database_name", "username",
        "connection_mode", "status", "created_at"
    }
    for key in required_keys:
        assert key in sample, f"Required field '{key}' not found in DataSource API response"

    # Verify defaults as per 04-integration-system-test-spec.md Section 2.3
    assert sample.get("ssh_port") == 22
    assert sample.get("is_read_only") is False

def test_query_result_response_shape_matches_types_ts(client, test_datasource):
    resp = client.post(
        "/api/v1/query/execute",
        json={"datasource_id": test_datasource.id, "sql": "SELECT 1"},
        headers={"X-Local-Token": LOCAL_SECURE_TOKEN}
    )
    assert resp.status_code == 200, resp.json()
    result = resp.json()

    # QueryResult fields check
    for field in {"columns", "rows", "rowCount", "latencyMs", "success"}:
        assert field in result, f"Field '{field}' not found in QueryResult response"

    # GuardrailCheckResult fields check
    assert "guardrail" in result
    guardrail = result["guardrail"]
    expected_guardrail = parse_types_ts_interface("GuardrailCheckResult")
    for field in expected_guardrail:
        assert field in guardrail, f"Field '{field}' not found in guardrail checks result: {guardrail}"

def test_trust_gate_result_matches_types_ts(db_session, test_datasource):
    tg = TrustGate(db_session, validate_sql_schema)
    result = tg.evaluate(test_datasource.id, "SELECT 1")
    
    expected_tg = parse_types_ts_interface("TrustGateResult")
    for key in expected_tg:
        assert key in result, f"Field '{key}' not found in TrustGate evaluate result"

@pytest.mark.parametrize("endpoint,payload,expected_code", [
    ("/api/v1/query/execute", {"datasource_id": "non-existent-ds", "sql": "SELECT 1"}, "DATASOURCE_NOT_FOUND"),
    ("/api/v1/datasources/non-existent/health", None, "NOT_FOUND"),
])
def test_error_response_always_has_detail_code_key(client, test_datasource, endpoint, payload, expected_code):
    if payload is not None:
        p = payload
        resp = client.post(endpoint, json=p, headers={"X-Local-Token": LOCAL_SECURE_TOKEN})
    else:
        resp = client.post(endpoint, headers={"X-Local-Token": LOCAL_SECURE_TOKEN})
    
    assert resp.status_code in (400, 404), resp.json()
    body = resp.json()
    assert "detail" in body and isinstance(body["detail"], dict)
    assert body["detail"]["code"] == expected_code
    assert "message" in body["detail"]

def test_error_response_for_guardrail_blocked(client, test_datasource):
    resp = client.post(
        "/api/v1/query/execute",
        json={"datasource_id": test_datasource.id, "sql": "DROP TABLE t"},
        headers={"X-Local-Token": LOCAL_SECURE_TOKEN}
    )
    assert resp.status_code == 400, resp.json()
    body = resp.json()
    assert "detail" in body and isinstance(body["detail"], dict)
    # PolicyEngine catches DDL before Guardrail, so the error code is DDL_BLOCKED
    assert body["detail"]["code"] in ("DDL_BLOCKED", "GUARDRAIL_BLOCKED")
    assert "message" in body["detail"]
