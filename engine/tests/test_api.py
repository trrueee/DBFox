"""API tests ????????md Section 18.3"""
import json

from fastapi.testclient import TestClient
from engine.main import app, LOCAL_SECURE_TOKEN
from engine.db import get_db
from engine.errors import DataSourceConnectionError
from engine.models import DEFAULT_PROJECT_ID, DataSource, QueryHistory, SchemaTable
from engine.agent_core.types import AgentRunResponse, AgentRuntimeEvent
from engine.tests.support.datasource import (
    sqlite_connection_test_payload,
    sqlite_datasource_create_payload,
)
import pytest


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with in-memory database override."""
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _headers():
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


# ============================================================
# DataSource endpoints
# ============================================================

def test_projects_default_exists(client) -> None:
    resp = client.get("/api/v1/projects", headers=_headers())
    assert resp.status_code == 200
    projects = resp.json()
    assert len(projects) == 1
    assert projects[0]["id"] == DEFAULT_PROJECT_ID
    assert projects[0]["name"] == "Default Workspace"


def test_create_project(client) -> None:
    resp = client.post("/api/v1/projects", json={
        "name": "Demo Product Workspace",
        "description": "Assets for lifecycle workflow tests",
    }, headers=_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] != DEFAULT_PROJECT_ID
    assert data["name"] == "Demo Product Workspace"
    assert data["description"] == "Assets for lifecycle workflow tests"
    assert data["datasource_count"] == 0


def test_test_connection_success(client, test_datasource) -> None:
    resp = client.post(
        "/api/v1/datasources/test",
        json=sqlite_connection_test_payload(test_datasource.database_name),
        headers=_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "tablesCount" in data


def test_test_connection_failure(client) -> None:
    resp = client.post("/api/v1/datasources/test", json={
        "host": "192.0.2.1",
        "port": 3306,
        "database_name": "nonexistent",
        "username": "nobody",
        "password": "wrong",
    }, headers=_headers())
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CONNECTION_FAILED"


def test_test_connection_mysql_unreachable_returns_connection_failed_not_500(client) -> None:
    """Regression: failed MySQL probe must not crash on undefined temp_tunnel."""
    resp = client.post(
        "/api/v1/datasources/test",
        json={
            "db_type": "mysql",
            "host": "127.0.0.1",
            "port": 3306,
            "database_name": "analytics",
            "username": "root",
            "password": "wrong",
            "ssh_enabled": False,
            "ssl_enabled": False,
        },
        headers=_headers(),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["code"] == "CONNECTION_FAILED"
    assert "temp_tunnel" not in str(body).lower()


def test_create_datasource(client, test_datasource) -> None:
    resp = client.post("/api/v1/datasources", json=sqlite_datasource_create_payload(
        test_datasource.database_name,
        name="api_test_db",
    ), headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["name"] == "api_test_db"
    assert data["status"] == "active"
    assert data["project_id"] == DEFAULT_PROJECT_ID


def test_create_datasource_can_attach_to_project(client, test_datasource) -> None:
    project_resp = client.post("/api/v1/projects", json={
        "name": "Project Datasource Test",
    }, headers=_headers())
    project_id = project_resp.json()["id"]

    resp = client.post("/api/v1/datasources", json=sqlite_datasource_create_payload(
        test_datasource.database_name,
        name="project_api_test_db",
        project_id=project_id,
    ), headers=_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == project_id


def test_list_datasources_can_filter_by_project(client, test_datasource) -> None:
    project_a = client.post("/api/v1/projects", json={"name": "Workspace A"}, headers=_headers()).json()
    project_b = client.post("/api/v1/projects", json={"name": "Workspace B"}, headers=_headers()).json()

    for project, name in [(project_a, "db_a"), (project_b, "db_b")]:
        resp = client.post("/api/v1/datasources", json=sqlite_datasource_create_payload(
            test_datasource.database_name,
            name=name,
            project_id=project["id"],
        ), headers=_headers())
        assert resp.status_code == 200

    resp = client.get(f"/api/v1/datasources?project_id={project_a['id']}", headers=_headers())
    assert resp.status_code == 200
    items = resp.json()
    assert [item["name"] for item in items] == ["db_a"]


def test_create_datasource_persists_ssl_settings(client, test_datasource) -> None:
    resp = client.post("/api/v1/datasources", json=sqlite_datasource_create_payload(
        test_datasource.database_name,
        name="ssl_test_db",
        ssl_enabled=True,
        ssl_ca_path="C:/certs/mysql-ca.pem",
        ssl_cert_path="C:/certs/client-cert.pem",
        ssl_key_path="C:/certs/client-key.pem",
        ssl_verify_identity=True,
    ), headers=_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["ssl_enabled"] is True
    assert data["ssl_ca_path"] == "C:/certs/mysql-ca.pem"
    assert data["ssl_cert_path"] == "C:/certs/client-cert.pem"
    assert data["ssl_key_path"] == "C:/certs/client-key.pem"
    assert data["ssl_verify_identity"] is True


def test_datasource_health_check_updates_snapshot(client, test_datasource) -> None:
    resp = client.post("/api/v1/datasources", json={
        "name": "health_test_db",
        "db_type": "sqlite",
        "host": "localhost",
        "port": 0,
        "database_name": test_datasource.database_name,
        "username": "test",
        "password": "test",
    }, headers=_headers())
    ds_id = resp.json()["id"]

    resp = client.post(f"/api/v1/datasources/{ds_id}/health", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "success"
    assert data["tablesCount"] >= 20
    assert isinstance(data["latencyMs"], int)
    assert data["datasource"]["last_test_status"] == "success"
    assert data["datasource"]["last_test_tables_count"] == data["tablesCount"]
    assert data["datasource"]["last_test_at"]


def test_datasource_health_check_failure_persists_snapshot(client, test_datasource, monkeypatch) -> None:
    import engine.api.datasources as datasources_api

    resp = client.post("/api/v1/datasources", json=sqlite_datasource_create_payload(
        test_datasource.database_name,
        name="health_failed_db",
    ), headers=_headers())
    ds_id = resp.json()["id"]

    def fail_connection(config: dict[str, object]) -> dict[str, object]:
        raise DataSourceConnectionError("??????")

    monkeypatch.setattr(datasources_api, "test_connection", fail_connection)

    resp = client.post(f"/api/v1/datasources/{ds_id}/health", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["status"] == "failed"
    assert data["message"] == "??????"
    assert data["datasource"]["last_test_status"] == "failed"
    assert data["datasource"]["last_test_error"] == "??????"


def test_sync_schema(client, db_session, test_datasource) -> None:
    ds_id = test_datasource.id

    # Sync
    resp = client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify tables in DB
    tables = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == ds_id
    ).all()
    assert len(tables) == 20


def test_list_tables(client, db_session, test_datasource) -> None:
    ds_id = test_datasource.id
    client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())

    # List tables
    resp = client.get(f"/api/v1/schema/tables?datasource_id={ds_id}", headers=_headers())
    assert resp.status_code == 200
    tables = resp.json()
    assert len(tables) == 20
    assert any(t["table_name"] == "users" for t in tables)
    assert all("id" in t for t in tables)
    assert all("columns_count" in t for t in tables)
    assert all("module_tag" in t for t in tables)


def test_list_columns(client, db_session, test_datasource) -> None:
    ds_id = test_datasource.id
    client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())

    # Get first table
    tables_resp = client.get(f"/api/v1/schema/tables?datasource_id={ds_id}", headers=_headers())
    tables = tables_resp.json()
    first_table_id = tables[0]["id"]

    # List columns
    resp = client.get(f"/api/v1/schema/tables/{first_table_id}/columns", headers=_headers())
    assert resp.status_code == 200
    columns = resp.json()
    assert len(columns) > 0
    assert all("column_name" in c for c in columns)
    assert all("data_type" in c for c in columns)


def test_validate_sql_datasource_not_found(client) -> None:
    resp = client.post("/api/v1/query/validate", json={
        "sql": "SELECT id, name FROM users LIMIT 10",
        "datasource_id": "nonexistent-ds-id-12345",
    }, headers=_headers())
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "DATASOURCE_NOT_FOUND"


def test_validate_sql_uses_datasource_db_type(client, db_session, monkeypatch) -> None:
    ds = DataSource(
        id="mock-pg-ds",
        name="mock_pg_ds",
        db_type="postgresql",
        host="localhost",
        port=5432,
        database_name="postgres",
        username="postgres",
        password_ciphertext="pwd",
        password_nonce="nonce",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    captured_dialect = None
    import engine.api.query as query_api

    def mock_guardrail_check(sql, dialect="mysql"):
        nonlocal captured_dialect
        captured_dialect = dialect
        return {
            "result": "pass",
            "originalSql": sql,
            "safeSql": sql,
            "checks": [],
            "message": "Passed"
        }

    monkeypatch.setattr(query_api, "guardrail_check", mock_guardrail_check)

    resp = client.post("/api/v1/query/validate", json={
        "sql": "SELECT * FROM users",
        "datasource_id": "mock-pg-ds",
    }, headers=_headers())

    assert resp.status_code == 200
    assert captured_dialect == "postgresql"


def test_validate_sql(client) -> None:
    resp = client.post("/api/v1/query/validate", json={
        "sql": "SELECT id, name FROM users LIMIT 10",
    }, headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] in ("pass", "warn", "reject")
    assert "safeSql" in data
    assert "checks" in data


def test_execute_sql_and_history(client, db_session, test_datasource) -> None:
    ds_id = test_datasource.id
    client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())

    # Execute SQL against demo SQLite
    resp = client.post("/api/v1/query/execute", json={
        "datasource_id": ds_id,
        "sql": "SELECT id, username, email FROM users LIMIT 5",
        "execution_id": "api-test-exec-id",
    }, headers=_headers())
    assert resp.status_code == 200, f"Execute failed: {resp.json()}"
    data = resp.json()
    assert data["success"] is True
    assert data["executionId"] == "api-test-exec-id"
    assert len(data["columns"]) == 3
    assert "username" in data["columns"]

    # Query history
    resp = client.get(f"/api/v1/query/history?datasource_id={ds_id}", headers=_headers())
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) >= 1
    assert history[0]["execution_status"] == "success"


def _mock_sql_generation(monkeypatch, sql: str = "SELECT id, username FROM users LIMIT 10") -> None:
    """API tests run without LLM credentials ??stub the SQL generator."""
    monkeypatch.setattr("engine.tools.sql_tools._render_sql_from_query_plan", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "engine.tools.sql_tools.generate_sql_from_schema_context",
        lambda *_a, **_k: {
            "sql": sql,
            "model": "test",
            "mode": "offline",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        },
    )


def test_agent_run_endpoint_review_mode(client, test_datasource, monkeypatch) -> None:
    _mock_sql_generation(monkeypatch)
    ds_id = test_datasource.id
    client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())

    resp = client.post("/api/v1/agent/run", json={
        "datasource_id": ds_id,
        "question": "list all users",
        "execute": False,
    }, headers=_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["run_id"]
    assert data["session_id"]
    assert data["context_summary"]
    assert data["sql"].upper().startswith("SELECT")
    assert data["safety"]["can_execute"] is True
    assert data["answer"]["evidence"]
    assert data["artifacts"]
    artifact_ids = {artifact["id"] for artifact in data["artifacts"]}
    assert {item["artifact_id"] for item in data["answer"]["evidence"]}.issubset(artifact_ids)
    assert data["message_blocks"][0]["type"] == "text"
    assert any(block["type"] == "answer" for block in data["message_blocks"])
    assert data["events"][0]["type"] == "agent.narration.completed"
    assert data["trace_events"]
    assert [step["name"] for step in data["steps"]] == [
        "build_schema_context",
        "generate_sql_candidate",
        "validate_sql",
        "execute_sql",
        "profile_result",
        "suggest_chart",
        "suggest_followups",
        "answer_synthesizer",
    ]


def test_agent_run_stream_endpoint_returns_sse_final_response(client, test_datasource, monkeypatch) -> None:
    _mock_sql_generation(monkeypatch)
    ds_id = test_datasource.id
    client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())

    resp = client.post("/api/v1/agent/run/stream", json={
        "datasource_id": ds_id,
        "question": "list users",
        "execute": False,
    }, headers=_headers())

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    chunks = [chunk for chunk in resp.text.strip().split("\n\n") if chunk.strip()]
    event_names: list[str] = []
    payloads: list[dict] = []
    for chunk in chunks:
        lines = chunk.splitlines()
        event_line = next(line for line in lines if line.startswith("event: "))
        data_line = next(line for line in lines if line.startswith("data: "))
        event_names.append(event_line.removeprefix("event: "))
        payloads.append(json.loads(data_line.removeprefix("data: ")))

    assert event_names[0] == "agent.run.started"
    assert "agent.step.started" in event_names
    assert "agent.step.completed" in event_names
    assert "agent.artifact.created" in event_names
    assert "agent.answer.completed" in event_names
    assert event_names[-1] == "agent.run.completed"
    assert [payload["sequence"] for payload in payloads] == list(range(1, len(payloads) + 1))
    final_response = payloads[-1]["response"]
    assert final_response["success"] is True

    assert final_response["run_id"] == payloads[-1]["run_id"]
    assert final_response["sql"].upper().startswith("SELECT")
    assert [step["name"] for step in final_response["steps"]] == [
        "build_schema_context",
        "generate_sql_candidate",
        "validate_sql",
        "execute_sql",
        "profile_result",
        "suggest_chart",
        "suggest_followups",
        "answer_synthesizer",
    ]
    streamed_semantic_ids = [artifact["semantic_id"] for artifact in final_response["artifacts"]]
    assert "query_plan" in streamed_semantic_ids
    assert "sql_candidate" in streamed_semantic_ids
    assert "safety_report" in streamed_semantic_ids

    fallback_resp = client.post("/api/v1/agent/run", json={
        "datasource_id": ds_id,
        "question": "list users",
        "execute": False,
    }, headers=_headers())
    assert fallback_resp.status_code == 200
    fallback = fallback_resp.json()
    assert final_response["success"] == fallback["success"]
    assert final_response["question"] == fallback["question"]
    assert final_response["sql"] == fallback["sql"]
    assert final_response["error"] == fallback["error"]
    assert [artifact["semantic_id"] for artifact in final_response["artifacts"]] == [
        artifact["semantic_id"] for artifact in fallback["artifacts"]
    ]


def test_agent_run_stream_normalizes_llm_auth_errors(client, test_datasource, monkeypatch) -> None:
    from engine.api import agent as agent_api

    class FailingRuntime:
        def __init__(self, db) -> None:
            pass

        def run_iter(self, req):
            raise RuntimeError(
                "Error code: 401 - {'error': {'message': 'Incorrect API key provided', "
                "'code': 'invalid_api_key'}}"
            )
            yield

    monkeypatch.setattr(agent_api, "DataBoxAgentRuntime", FailingRuntime)

    resp = client.post("/api/v1/agent/run/stream", json={
        "datasource_id": test_datasource.id,
        "question": "hello",
        "execute": False,
        "api_key": "sk-test",
    }, headers=_headers())

    assert resp.status_code == 200
    payload = json.loads(resp.text.strip().splitlines()[-1].removeprefix("data: "))
    assert payload["type"] == "agent.run.failed"
    assert payload["code"] == "LLM_AUTH_ERROR"
    assert "API Key" in payload["error"]


def test_agent_run_endpoint_accepts_followup_context(client, test_datasource, monkeypatch) -> None:
    _mock_sql_generation(monkeypatch, sql="SELECT role, COUNT(*) AS cnt FROM users GROUP BY role")
    ds_id = test_datasource.id
    client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())

    resp = client.post("/api/v1/agent/run", json={
        "datasource_id": ds_id,
        "question": "Break it down by role",
        "execute": False,
        "follow_up_context": {
            "session_id": "api-session",
            "parent_run_id": "api-parent-run",
            "previous_question": "List users",
            "previous_answer": "The previous result listed users.",
            "artifacts": [
                {
                    "id": "sql_candidate",
                    "type": "sql",
                    "title": "Validated SQL",
                    "summary": "SELECT id, username, role FROM users LIMIT 5",
                    "payload": {"sql": "SELECT id, username, role FROM users LIMIT 5"},
                }
            ],
        },
    }, headers=_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["session_id"] == "api-session"
    assert data["parent_run_id"] == "api-parent-run"
    assert data["referenced_artifact_ids"] == ["sql_candidate"]
    assert data["steps"][0]["name"] == "load_follow_up_context"


def test_query_history_search_status_and_datasource_filter(client, db_session, test_datasource) -> None:
    ds1 = DataSource(
        id="history-ds-1",
        name="history_ds_1",
        host="localhost",
        port=0,
        database_name=test_datasource.database_name,
        username="test",
        password_ciphertext="test",
        password_nonce="test",
        db_type="sqlite",
        status="active",
    )
    ds2 = DataSource(
        id="history-ds-2",
        name="history_ds_2",
        host="localhost",
        port=0,
        database_name=test_datasource.database_name,
        username="test",
        password_ciphertext="test",
        password_nonce="test",
        db_type="sqlite",
        status="active",
    )
    db_session.add_all([ds1, ds2])
    db_session.flush()
    db_session.add_all([
        QueryHistory(
            id="history-success-users",
            data_source_id=ds1.id,
            question="list users",
            submitted_sql="SELECT * FROM users LIMIT 10",
            guardrail_result="warn",
            execution_status="success",
            execution_time_ms=12,
            rows_returned=3,
            columns_returned=4,
        ),
        QueryHistory(
            id="history-failed-orders",
            data_source_id=ds1.id,
            question="find failed orders",
            submitted_sql="SELECT * FROM orders LIMIT 10",
            guardrail_result="pass",
            execution_status="failed",
            execution_time_ms=5,
            rows_returned=0,
            columns_returned=0,
            error_message="orders table failed",
        ),
        QueryHistory(
            id="history-other-customers",
            data_source_id=ds2.id,
            question="customers",
            submitted_sql="SELECT * FROM customers LIMIT 10",
            guardrail_result="pass",
            execution_status="success",
            execution_time_ms=8,
            rows_returned=1,
            columns_returned=2,
        ),
    ])
    db_session.commit()

    resp = client.get(
        "/api/v1/query/history?datasource_id=history-ds-1&search=orders&status=failed&limit=10",
        headers=_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert [item["id"] for item in data] == ["history-failed-orders"]
    assert data[0]["execution_status"] == "failed"
    assert data[0]["execution_time_ms"] == 5

    resp = client.get("/api/v1/query/history?search=customers", headers=_headers())
    assert resp.status_code == 200
    assert [item["id"] for item in resp.json()] == ["history-other-customers"]

    resp = client.get("/api/v1/query/history?status=unknown", headers=_headers())
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_HISTORY_STATUS"


def test_query_history_delete_and_clear(client, db_session, test_datasource) -> None:
    ds1 = DataSource(
        id="history-clear-ds-1",
        name="history_clear_ds_1",
        host="localhost",
        port=0,
        database_name=test_datasource.database_name,
        username="test",
        password_ciphertext="test",
        password_nonce="test",
        db_type="sqlite",
        status="active",
    )
    ds2 = DataSource(
        id="history-clear-ds-2",
        name="history_clear_ds_2",
        host="localhost",
        port=0,
        database_name=test_datasource.database_name,
        username="test",
        password_ciphertext="test",
        password_nonce="test",
        db_type="sqlite",
        status="active",
    )
    db_session.add_all([ds1, ds2])
    db_session.flush()
    db_session.add_all([
        QueryHistory(
            id="history-delete-one",
            data_source_id=ds1.id,
            submitted_sql="SELECT 1",
            guardrail_result="pass",
            execution_status="success",
        ),
        QueryHistory(
            id="history-clear-one",
            data_source_id=ds1.id,
            submitted_sql="SELECT 2",
            guardrail_result="pass",
            execution_status="success",
        ),
        QueryHistory(
            id="history-keep-other-ds",
            data_source_id=ds2.id,
            submitted_sql="SELECT 3",
            guardrail_result="pass",
            execution_status="success",
        ),
    ])
    db_session.commit()

    resp = client.delete("/api/v1/query/history/history-delete-one", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    assert db_session.query(QueryHistory).filter(QueryHistory.id == "history-delete-one").first() is None

    resp = client.delete("/api/v1/query/history?datasource_id=history-clear-ds-1", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    assert db_session.query(QueryHistory).filter(QueryHistory.data_source_id == ds1.id).count() == 0
    assert db_session.query(QueryHistory).filter(QueryHistory.data_source_id == ds2.id).count() == 1

    resp = client.delete("/api/v1/query/history/missing-history", headers=_headers())
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "QUERY_HISTORY_NOT_FOUND"


def test_cancel_unknown_query(client) -> None:
    resp = client.post("/api/v1/query/cancel", json={
        "execution_id": "missing-execution-id",
    }, headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["cancelled"] is False
    assert data["executionId"] == "missing-execution-id"


def test_conversations_crud(client) -> None:
    payload = {
        "id": "conversation-test-1",
        "title": "??",
        "created_at": 1_700_000_000_000,
        "updated_at": 1_700_000_100_000,
        "context_tables_json": "[]",
        "messages_json": '[{"id":"m1","role":"user","content":"??","createdAt":1}]',
        "artifacts_json": "[]",
    }
    resp = client.put("/api/v1/conversations/conversation-test-1", json=payload, headers=_headers())
    assert resp.status_code == 200

    resp = client.get("/api/v1/conversations", headers=_headers())
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["title"] == "??"

    resp = client.delete("/api/v1/conversations/conversation-test-1", headers=_headers())
    assert resp.status_code == 200
    resp = client.get("/api/v1/conversations", headers=_headers())
    assert resp.json() == []
