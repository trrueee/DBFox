import pytest
import re
from pathlib import Path
from fastapi.testclient import TestClient
from engine.main import app, LOCAL_SECURE_TOKEN
from engine.models import DataSource, QueryHistory
from engine.crypto import encrypt_password
from engine.errors import DBFoxError
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
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        test_client.close()

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


def test_sqlite_datasource_response_serializes_nullable_connection_fields():
    from engine.api.datasources import _datasource_to_dict

    cipher, nonce = encrypt_password("")
    ds = DataSource(
        id="ds-sqlite-null-host",
        project_id="default",
        name="sqlite_contract",
        db_type="sqlite",
        host=None,
        port=0,
        database_name="/tmp/local.db",
        username=None,
        password_ciphertext=cipher,
        password_nonce=nonce,
        is_read_only=False,
        ssh_enabled=False,
        ssl_enabled=False,
        ssl_verify_identity=True,
        status="active",
    )

    sample = _datasource_to_dict(ds)

    assert sample["host"] == ""
    assert sample["username"] == ""


def test_delete_datasource_accepts_confirmation_in_request_body(client, db_session, monkeypatch):
    monkeypatch.setenv("DBFOX_BYPASS_CONFIRMATION", "0")
    cipher, nonce = encrypt_password("")
    ds = DataSource(
        id="ds-delete-body",
        project_id="default",
        name="delete_body_contract",
        db_type="sqlite",
        host="",
        port=0,
        database_name="/tmp/local.db",
        username="",
        password_ciphertext=cipher,
        password_nonce=nonce,
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    first = client.request(
        "DELETE",
        "/api/v1/datasources/ds-delete-body",
        headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
    )
    assert first.status_code == 200, first.json()
    payload = first.json()
    assert payload["requires_confirmation"] is True

    second = client.request(
        "DELETE",
        "/api/v1/datasources/ds-delete-body",
        json={
            "confirm_token": payload["confirm_token"],
            "confirm_text": "delete_body_contract",
        },
        headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
    )

    assert second.status_code == 200, second.json()
    assert second.json()["success"] is True
    assert db_session.query(DataSource).filter(DataSource.id == "ds-delete-body").first() is None


def test_datasource_health_sanitizes_dbfox_error_message(client, db_session, monkeypatch):
    from engine.api.datasources import health as datasource_health_module

    cipher, nonce = encrypt_password("")
    ds = DataSource(
        id="ds-health-sanitize",
        project_id="default",
        name="health_sanitize_contract",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name="prod",
        username="root",
        password_ciphertext=cipher,
        password_nonce=nonce,
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    def fail_connection(_config):
        raise DBFoxError(
            message="connection failed for mysql://root:secret@127.0.0.1/prod password=secret",
            code="CONNECTION_FAILED",
        )

    monkeypatch.setattr(datasource_health_module, "test_connection", fail_connection)

    resp = client.post(
        "/api/v1/datasources/ds-health-sanitize/health",
        headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
    )

    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["ok"] is False
    assert "secret" not in body["message"]
    assert "mysql://root" not in body["message"]
    assert "[REDACTED]" in body["message"]

    db_session.refresh(ds)
    assert ds.last_test_error is not None
    assert "secret" not in ds.last_test_error
    assert "mysql://root" not in ds.last_test_error


def test_list_tables_reports_auto_sync_failure(client, db_session, monkeypatch):
    from engine.api.datasources import schema as datasource_schema_module

    cipher, nonce = encrypt_password("")
    ds = DataSource(
        id="ds-auto-sync-failure",
        project_id="default",
        name="auto_sync_failure_contract",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name="prod",
        username="root",
        password_ciphertext=cipher,
        password_nonce=nonce,
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    def fail_sync(_db, _datasource_id):
        raise RuntimeError("sync failed for mysql://root:secret@127.0.0.1/prod password=secret")

    monkeypatch.setattr(datasource_schema_module, "_sync_catalog", fail_sync)

    resp = client.get(
        "/api/v1/schema/tables?datasource_id=ds-auto-sync-failure",
        headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
    )

    assert resp.status_code == 400, resp.json()
    detail = resp.json()["detail"]
    assert detail["code"] == "SYNC_FAILED"
    assert "secret" not in detail["message"]
    assert "mysql://root" not in detail["message"]
    assert "[REDACTED]" in detail["message"]


def test_query_history_response_sanitizes_legacy_sensitive_fields(client, db_session, test_datasource):
    history = QueryHistory(
        id="history-legacy-sensitive",
        data_source_id=test_datasource.id,
        question="Find alice@example.com",
        submitted_sql="SELECT * FROM users WHERE email = 'alice@example.com'",
        generated_sql="SELECT * FROM users WHERE token = 'raw-token'",
        safe_sql="SELECT * FROM users WHERE password = 'plain-secret'",
        executed_sql="SELECT * FROM users WHERE phone = '13800138000'",
        guardrail_result="pass",
        execution_status="failed",
        rows_returned=0,
        columns_returned=0,
        error_message="driver leaked sk-live-secret1234567890",
    )
    db_session.add(history)
    db_session.commit()

    resp = client.get(
        f"/api/v1/query/history?datasource_id={test_datasource.id}",
        headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
    )

    assert resp.status_code == 200, resp.json()
    payload = next(item for item in resp.json() if item["id"] == "history-legacy-sensitive")
    serialized = str(payload)
    assert "alice@example.com" not in serialized
    assert "raw-token" not in serialized
    assert "plain-secret" not in serialized
    assert "13800138000" not in serialized
    assert "sk-live-secret1234567890" not in serialized
    assert "[REDACTED_EMAIL]" in serialized


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
