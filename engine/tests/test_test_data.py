from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import DataSource, SchemaTable, SchemaColumn


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def test_generate_test_data_success(client, db_session) -> None:
    # 1. Setup a mockup database datasource
    resp = client.post("/api/v1/datasources", json={
        "name": "test_data_source",
        "host": "demo",
        "port": 3306,
        "database_name": "demo_shop",
        "username": "demo",
        "password": "demo",
    }, headers=_headers())
    assert resp.status_code == 200
    ds_id = resp.json()["id"]

    # 2. Sync to populate the metastore
    sync_resp = client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())
    assert sync_resp.status_code == 200

    # 3. Choose a table in the synced demo (e.g. users)
    resp = client.get(f"/api/v1/schema/tables?datasource_id={ds_id}", headers=_headers())
    tables = resp.json()
    assert len(tables) > 0
    users_table = next(t for t in tables if t["table_name"] == "users")

    # 4. Generate test data for 'users'
    gen_resp = client.post("/api/v1/schema/generate-test-data", json={
        "datasource_id": ds_id,
        "table_name": "users",
        "row_count": 5,
        "language": "zh"
    }, headers=_headers())
    
    assert gen_resp.status_code == 200, f"Failed: {gen_resp.json()}"
    data = gen_resp.json()
    assert data["success"] is True
    assert data["insertedRows"] == 5
    assert "users" in data["tableName"]
    
    # 5. Query user preview data to confirm the data is inserted
    exec_resp = client.post("/api/v1/query/execute", json={
        "datasource_id": ds_id,
        "sql": "SELECT id, username, email FROM users LIMIT 10",
        "execution_id": "test-data-preview-exec",
    }, headers=_headers())
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["success"] is True
    assert len(exec_data["rows"]) >= 5
