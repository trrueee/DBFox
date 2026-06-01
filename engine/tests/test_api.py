"""API tests — 对应第一版.md Section 18.3"""
from fastapi.testclient import TestClient
from engine.main import app, LOCAL_SECURE_TOKEN
from engine.db import get_db
from engine.errors import DataSourceConnectionError
from engine.models import DEFAULT_PROJECT_ID, DataSource, QueryHistory, SchemaTable
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


def test_test_connection_success(client) -> None:
    resp = client.post("/api/v1/datasources/test", json={
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())
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


def test_create_datasource(client) -> None:
    resp = client.post("/api/v1/datasources", json={
        "name": "api_test_db",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["name"] == "api_test_db"
    assert data["status"] == "active"
    assert data["project_id"] == DEFAULT_PROJECT_ID


def test_create_datasource_can_attach_to_project(client) -> None:
    project_resp = client.post("/api/v1/projects", json={
        "name": "Project Datasource Test",
    }, headers=_headers())
    project_id = project_resp.json()["id"]

    resp = client.post("/api/v1/datasources", json={
        "project_id": project_id,
        "name": "project_api_test_db",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == project_id


def test_list_datasources_can_filter_by_project(client) -> None:
    project_a = client.post("/api/v1/projects", json={"name": "Workspace A"}, headers=_headers()).json()
    project_b = client.post("/api/v1/projects", json={"name": "Workspace B"}, headers=_headers()).json()

    for project, name in [(project_a, "db_a"), (project_b, "db_b")]:
        resp = client.post("/api/v1/datasources", json={
            "project_id": project["id"],
            "name": name,
            "host": "demo",
            "port": 3306,
            "database_name": "demo_shop",
            "username": "demo",
            "password": "demo",
        }, headers=_headers())
        assert resp.status_code == 200

    resp = client.get(f"/api/v1/datasources?project_id={project_a['id']}", headers=_headers())
    assert resp.status_code == 200
    items = resp.json()
    assert [item["name"] for item in items] == ["db_a"]


def test_create_datasource_persists_ssl_settings(client) -> None:
    resp = client.post("/api/v1/datasources", json={
        "name": "ssl_test_db",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
        "ssl_enabled": True,
        "ssl_ca_path": "C:/certs/mysql-ca.pem",
        "ssl_cert_path": "C:/certs/client-cert.pem",
        "ssl_key_path": "C:/certs/client-key.pem",
        "ssl_verify_identity": True,
    }, headers=_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["ssl_enabled"] is True
    assert data["ssl_ca_path"] == "C:/certs/mysql-ca.pem"
    assert data["ssl_cert_path"] == "C:/certs/client-cert.pem"
    assert data["ssl_key_path"] == "C:/certs/client-key.pem"
    assert data["ssl_verify_identity"] is True


def test_datasource_health_check_updates_snapshot(client) -> None:
    resp = client.post("/api/v1/datasources", json={
        "name": "health_test_db",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())
    ds_id = resp.json()["id"]

    resp = client.post(f"/api/v1/datasources/{ds_id}/health", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "success"
    assert data["readonly"] is True
    assert data["tablesCount"] == 20
    assert isinstance(data["latencyMs"], int)
    assert data["datasource"]["last_test_status"] == "success"
    assert data["datasource"]["last_test_readonly"] is True
    assert data["datasource"]["last_test_tables_count"] == 20
    assert data["datasource"]["last_test_at"]


def test_datasource_health_check_failure_persists_snapshot(client, monkeypatch) -> None:
    import engine.api.datasources as datasources_api

    resp = client.post("/api/v1/datasources", json={
        "name": "health_failed_db",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())
    ds_id = resp.json()["id"]

    def fail_connection(config: dict[str, object]) -> dict[str, object]:
        raise DataSourceConnectionError("模拟连接失败")

    monkeypatch.setattr(datasources_api, "test_connection", fail_connection)

    resp = client.post(f"/api/v1/datasources/{ds_id}/health", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["status"] == "failed"
    assert data["message"] == "模拟连接失败"
    assert data["datasource"]["last_test_status"] == "failed"
    assert data["datasource"]["last_test_error"] == "模拟连接失败"


def test_sync_schema(client, db_session) -> None:
    # Create datasource first
    resp = client.post("/api/v1/datasources", json={
        "name": "sync_test",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())
    ds_id = resp.json()["id"]

    # Sync
    resp = client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify tables in DB
    tables = db_session.query(SchemaTable).filter(
        SchemaTable.data_source_id == ds_id
    ).all()
    assert len(tables) == 20


def test_list_tables(client, db_session) -> None:
    # Setup: create + sync
    resp = client.post("/api/v1/datasources", json={
        "name": "list_test",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())
    ds_id = resp.json()["id"]
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


def test_list_columns(client, db_session) -> None:
    # Setup
    resp = client.post("/api/v1/datasources", json={
        "name": "col_test",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())
    ds_id = resp.json()["id"]
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


def test_validate_sql(client) -> None:
    resp = client.post("/api/v1/query/validate", json={
        "sql": "SELECT id, name FROM users LIMIT 10",
    }, headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] in ("pass", "warn", "reject")
    assert "safeSql" in data
    assert "checks" in data


def test_execute_sql_and_history(client, db_session) -> None:
    # Setup
    resp = client.post("/api/v1/datasources", json={
        "name": "exec_test",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())
    ds_id = resp.json()["id"]
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


def test_agent_run_endpoint_review_mode(client) -> None:
    resp = client.post("/api/v1/datasources", json={
        "name": "agent_endpoint_test",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())
    ds_id = resp.json()["id"]
    client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())

    resp = client.post("/api/v1/query/agent-run", json={
        "datasource_id": ds_id,
        "question": "查询所有用户",
        "execute": False,
    }, headers=_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["sql"].upper().startswith("SELECT")
    assert data["safety"]["can_execute"] is True
    assert [step["name"] for step in data["steps"]] == [
        "build_schema_context",
        "build_query_plan",
        "generate_sql_candidate",
        "validate_sql",
        "execute_sql",
        "explain_result",
        "suggest_chart",
    ]


def test_query_history_search_status_and_datasource_filter(client, db_session) -> None:
    ds1 = DataSource(
        id="history-ds-1",
        name="history_ds_1",
        host="demo",
        port=3306,
        database_name="demo_shop",
        username="demo",
        password_ciphertext="test",
        password_nonce="test",
        status="active",
    )
    ds2 = DataSource(
        id="history-ds-2",
        name="history_ds_2",
        host="demo",
        port=3306,
        database_name="demo_shop",
        username="demo",
        password_ciphertext="test",
        password_nonce="test",
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


def test_query_history_delete_and_clear(client, db_session) -> None:
    ds1 = DataSource(
        id="history-clear-ds-1",
        name="history_clear_ds_1",
        host="demo",
        port=3306,
        database_name="demo_shop",
        username="demo",
        password_ciphertext="test",
        password_nonce="test",
        status="active",
    )
    ds2 = DataSource(
        id="history-clear-ds-2",
        name="history_clear_ds_2",
        host="demo",
        port=3306,
        database_name="demo_shop",
        username="demo",
        password_ciphertext="test",
        password_nonce="test",
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
