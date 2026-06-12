from fastapi.testclient import TestClient
from engine.main import app
from engine.dev_server import _RELOAD_EXCLUDES

def test_fastapi_app_startup_and_health() -> None:
    """
    Sprint 0 / Hotfix startup gate:
    Verify that the FastAPI application can be imported successfully
    without any ModuleNotFoundError, and that the health endpoint
    returns status 200 with standard health indicators.
    """
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert data["version"] == "1.0.0"


def test_dev_reload_excludes_avoid_root_runtime_and_frontend_dirs() -> None:
    """
    Uvicorn/WatchFiles can stall on Windows when the backend reload watcher is
    given broad excludes for root-level runtime or frontend dependency folders.
    The backend reload root is engine/, so these folders are outside its scope.
    """
    assert "**/.databox_runtime/**" not in _RELOAD_EXCLUDES
    assert "**/node_modules/**" not in _RELOAD_EXCLUDES
