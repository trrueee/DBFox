from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from engine.main import app, LOCAL_SECURE_TOKEN
from engine.db import get_db
from engine.models import DataSource
import pytest

@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def _headers():
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}

@patch("engine.demo_mysql.check_docker_available")
@patch("engine.demo_mysql.launch_demo_container")
@patch("engine.demo_mysql.wait_for_mysql_port")
@patch("engine.demo_mysql.populate_demo_data")
def test_api_start_demo_mysql_success(
    mock_populate,
    mock_wait,
    mock_launch,
    mock_docker_avail,
    client,
    db_session
) -> None:
    # 1. Setup mocks
    mock_docker_avail.return_value = True
    mock_launch.return_value = True
    mock_wait.return_value = True
    mock_populate.return_value = None

    # Mock the schema sync to prevent actual mysql querying in tests
    with patch("engine.api.projects.sync_schema") as mock_sync:
        mock_sync.return_value = {"ok": True, "tablesCount": 20}
        
        # 2. Make request
        resp = client.post("/api/v1/demo/start", headers=_headers())
        
        # 3. Asserts
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert data["host"] == "127.0.0.1"
        assert data["port"] == 3309
        assert data["database_name"] == "databox_demo"
        assert data["username"] == "databox_demo_user"
        
        # Verify it was persisted in SQLite local DB
        ds = db_session.query(DataSource).filter(
            DataSource.host == "127.0.0.1",
            DataSource.port == 3309
        ).first()
        assert ds is not None
        assert ds.database_name == "databox_demo"

@patch("engine.demo_mysql.check_docker_available")
def test_api_start_demo_mysql_no_docker(mock_docker_avail, client) -> None:
    mock_docker_avail.return_value = False
    
    resp = client.post("/api/v1/demo/start", headers=_headers())
    assert resp.status_code == 400
    err_detail = resp.json()["detail"]
    assert err_detail["code"] == "DOCKER_NOT_AVAILABLE"
    assert "未检测到本地 Docker" in err_detail["message"]
