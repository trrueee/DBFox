from pathlib import Path

from fastapi.testclient import TestClient

from engine.main import LOCAL_SECURE_TOKEN, app
import engine.main as main_module
from engine.dev_server import _RELOAD_EXCLUDES
from engine.dev_server import bind_engine_socket
import engine.dev_server as dev_server_module

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
    assert data["version"] == "1.0.2"


def test_dev_reload_excludes_avoid_root_runtime_and_frontend_dirs() -> None:
    """
    Uvicorn/WatchFiles can stall on Windows when the backend reload watcher is
    given broad excludes for root-level runtime or frontend dependency folders.
    The backend reload root is engine/, so these folders are outside its scope.
    """
    assert "**/.dbfox_runtime/**" not in _RELOAD_EXCLUDES
    assert "**/node_modules/**" not in _RELOAD_EXCLUDES


def test_bind_engine_socket_returns_actual_ephemeral_port() -> None:
    sock, port = bind_engine_socket(0)
    try:
        assert port > 0
        assert sock.getsockname()[0] == "127.0.0.1"
        assert sock.getsockname()[1] == port
    finally:
        sock.close()


def test_frozen_engine_allows_tauri_localhost_origins(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "is_frozen", True)

    with TestClient(app) as client:
        for origin in ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"]:
            response = client.get(
                "/api/v1/datasources",
                headers={
                    "Origin": origin,
                    "X-Local-Token": LOCAL_SECURE_TOKEN,
                },
            )

            assert response.status_code != 403
            assert response.headers.get("access-control-allow-origin") == origin


def test_frozen_engine_allows_health_without_origin(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "is_frozen", True)

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_protected_routes_compare_local_token_in_constant_time(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_compare_digest(left: str, right: str) -> bool:
        calls.append((left, right))
        return True

    monkeypatch.setattr(main_module.secrets, "compare_digest", fake_compare_digest)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/datasources",
            headers={"X-Local-Token": "token-from-request"},
        )

    assert calls == [("token-from-request", LOCAL_SECURE_TOKEN)]
    assert response.status_code != 401


def test_source_engine_never_writes_a_workspace_frontend_env_file() -> None:
    """Source mode must not place a live engine token in the repository."""
    source = Path(main_module.__file__).read_text(encoding="utf-8")
    dev_server_source = Path(dev_server_module.__file__).read_text(encoding="utf-8")

    assert "desktop/.env.local" not in source
    assert "VITE_LOCAL_ENGINE_TOKEN" not in source
    assert ".env.local" not in dev_server_source
