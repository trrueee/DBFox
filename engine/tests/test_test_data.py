import sqlite3

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import DataSource, SchemaTable, SchemaColumn
from engine.tests.support.datasource import sqlite_datasource_create_payload


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


def _count_users(database_path: str) -> int:
    with sqlite3.connect(database_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        return int(cursor.fetchone()[0])


def test_generate_test_data_success(client, db_session, test_datasource) -> None:
    resp = client.post("/api/v1/datasources", json=sqlite_datasource_create_payload(
        test_datasource.database_name,
        name="test_data_source",
    ), headers=_headers())
    assert resp.status_code == 200
    ds_id = resp.json()["id"]

    # 2. Sync to populate the metastore
    sync_resp = client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())
    assert sync_resp.status_code == 200

    # 3. Choose a table in the synced test DB (e.g. users)
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
    
    # 5. Confirm the generator wrote rows into the target SQLite table.
    assert _count_users(test_datasource.database_name) >= 5


def test_generate_test_data_confirmation_binds_language(client, test_datasource, monkeypatch) -> None:
    class FakeConfirmationManager:
        def __init__(self) -> None:
            self.created_details: dict[str, object] | None = None

        def create_confirmation(self, datasource_id: str, action: str, details: dict[str, object], expected_confirm_text: str) -> str:
            self.created_details = details
            return "test-data-token"

        def validate_and_consume(
            self,
            token: str,
            confirm_text: str,
            *,
            expected_action: str,
            expected_datasource_id: str,
            expected_details: dict[str, object],
        ) -> tuple[bool, str]:
            assert token == "test-data-token"
            assert confirm_text == test_datasource.name
            assert expected_action == "generate_test_data"
            assert expected_datasource_id == test_datasource.id
            if self.created_details != expected_details:
                return False, "details mismatch"
            return True, ""

    manager = FakeConfirmationManager()
    monkeypatch.setattr("engine.policy.confirmation_bypass_enabled", lambda: False)
    monkeypatch.setattr("engine.policy.confirmation_manager", manager)

    resp = client.post("/api/v1/schema/generate-test-data", json={
        "datasource_id": test_datasource.id,
        "table_name": "users",
        "row_count": 5,
        "language": "zh",
    }, headers=_headers())

    assert resp.status_code == 200
    confirmation = resp.json()
    assert confirmation["requires_confirmation"] is True
    assert manager.created_details == {"table_name": "users", "row_count": 5, "language": "zh"}

    resp = client.post("/api/v1/schema/generate-test-data", json={
        "datasource_id": test_datasource.id,
        "table_name": "users",
        "row_count": 5,
        "language": "en",
        "confirm_token": confirmation["confirm_token"],
        "confirm_text": test_datasource.name,
    }, headers=_headers())

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CONFIRMATION_FAILED"
