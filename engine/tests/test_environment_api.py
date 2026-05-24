from subprocess import CompletedProcess

import pytest
from fastapi.testclient import TestClient

from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import DEFAULT_PROJECT_ID


def _headers():
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _patch_environment_create(monkeypatch) -> None:
    monkeypatch.setattr("engine.environment.ensure_docker_available", lambda: None)
    monkeypatch.setattr("engine.environment.allocate_local_port", lambda: 3311)
    monkeypatch.setattr(
        "engine.environment._run_docker",
        lambda args, timeout=30: CompletedProcess(args=args, returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr("engine.environment.wait_for_mysql_port", lambda timeout=60, port=3311: True)
    monkeypatch.setattr(
        "engine.environment.populate_demo_data",
        lambda port=3311, root_password="", database_name="": None,
    )
    monkeypatch.setattr("engine.api.sync_schema", lambda db, datasource_id: {"ok": True})


def test_create_and_list_local_mysql_environment(client, monkeypatch) -> None:
    _patch_environment_create(monkeypatch)

    resp = client.post(
        "/api/v1/environments/local-mysql",
        json={"project_id": DEFAULT_PROJECT_ID, "name": "Local Dev MySQL", "seed_demo": True},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.json()
    environment = resp.json()
    assert environment["project_id"] == DEFAULT_PROJECT_ID
    assert environment["name"] == "Local Dev MySQL"
    assert environment["runtime"] == "docker"
    assert environment["engine_type"] == "mysql"
    assert environment["status"] == "running"
    assert environment["datasource_id"]

    resp = client.get(f"/api/v1/projects/{DEFAULT_PROJECT_ID}/environments", headers=_headers())
    assert resp.status_code == 200
    environments = resp.json()
    assert len(environments) == 1
    assert environments[0]["id"] == environment["id"]

    resp = client.get(f"/api/v1/datasources?project_id={DEFAULT_PROJECT_ID}", headers=_headers())
    assert resp.status_code == 200
    datasource = resp.json()[0]
    assert datasource["environment_id"] == environment["id"]
    assert datasource["id"] == environment["datasource_id"]


def test_environment_operations(client, monkeypatch) -> None:
    _patch_environment_create(monkeypatch)
    create_resp = client.post(
        "/api/v1/environments/local-mysql",
        json={"project_id": DEFAULT_PROJECT_ID, "name": "Ops MySQL"},
        headers=_headers(),
    )
    environment_id = create_resp.json()["id"]

    monkeypatch.setattr("engine.api.stop_environment", lambda environment: setattr(environment, "status", "stopped"))
    resp = client.post(f"/api/v1/environments/{environment_id}/stop", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"

    monkeypatch.setattr("engine.api.start_environment", lambda environment: setattr(environment, "status", "running"))
    resp = client.post(f"/api/v1/environments/{environment_id}/start", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    def fake_health(environment):
        environment.last_health_status = "healthy"
        return {"status": "healthy", "containerStatus": "running", "tcpOk": True, "mysqlOk": True, "error": None}

    monkeypatch.setattr("engine.api.check_environment_health", fake_health)
    resp = client.get(f"/api/v1/environments/{environment_id}/health", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["health"]["status"] == "healthy"

    monkeypatch.setattr("engine.api.get_environment_logs", lambda environment, tail=200: "mysql ready")
    resp = client.get(f"/api/v1/environments/{environment_id}/logs", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["logs"] == "mysql ready"


def test_docker_status_and_lifecycle(client, monkeypatch) -> None:
    # 1. Test docker-status API
    monkeypatch.setattr("engine.demo_mysql.check_docker_available", lambda: True)
    resp = client.get("/api/v1/environments/docker-status", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["available"] is True

    monkeypatch.setattr("engine.demo_mysql.check_docker_available", lambda: False)
    resp = client.get("/api/v1/environments/docker-status", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["available"] is False

    # 2. Setup mock environment for destroy and rebuild
    _patch_environment_create(monkeypatch)
    create_resp = client.post(
        "/api/v1/environments/local-mysql",
        json={"project_id": DEFAULT_PROJECT_ID, "name": "Lifecycle MySQL"},
        headers=_headers(),
    )
    assert create_resp.status_code == 200
    environment = create_resp.json()
    environment_id = environment["id"]

    # Test rebuild environment
    monkeypatch.setattr("engine.environment.ensure_docker_available", lambda: None)
    monkeypatch.setattr("engine.environment.wait_for_mysql_port", lambda timeout=60, port=3311: True)
    monkeypatch.setattr("engine.environment.decrypt_password", lambda c, n: "fake_password")
    monkeypatch.setattr(
        "engine.environment._run_docker",
        lambda args, timeout=30: CompletedProcess(args=args, returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        "engine.environment.populate_demo_data",
        lambda port=3311, root_password="", database_name="": None,
    )
    monkeypatch.setattr("engine.api.sync_schema", lambda db, datasource_id: {"ok": True})

    resp = client.post(f"/api/v1/environments/{environment_id}/rebuild", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    # Test destroy environment
    resp = client.delete(f"/api/v1/environments/{environment_id}", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Ensure it's not found in list or datasource
    resp = client.get(f"/api/v1/projects/{DEFAULT_PROJECT_ID}/environments", headers=_headers())
    assert resp.status_code == 200
    assert len(resp.json()) == 0

