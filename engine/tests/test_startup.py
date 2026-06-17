import runpy
from pathlib import Path

from fastapi.testclient import TestClient
from engine.main import LOCAL_SECURE_TOKEN, app
import engine.main as main_module
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
    assert "**/.dbfox_runtime/**" not in _RELOAD_EXCLUDES
    assert "**/node_modules/**" not in _RELOAD_EXCLUDES


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


def test_dev_frontend_env_writer_skips_user_owned_env_file(monkeypatch) -> None:
    writes: list[str] = []
    user_owned_content = "VITE_CUSTOM_FLAG=1\n"
    original_exists = Path.exists
    original_read_text = Path.read_text
    original_write_text = Path.write_text

    def is_frontend_env_file(path: Path) -> bool:
        return path.name == ".env.local" and path.parent.name == "desktop"

    def fake_exists(path: Path) -> bool:
        if is_frontend_env_file(path):
            return True
        return original_exists(path)

    def fake_read_text(path: Path, *args, **kwargs) -> str:
        if is_frontend_env_file(path):
            return user_owned_content
        return original_read_text(path, *args, **kwargs)

    def fake_write_text(path: Path, data: str, *args, **kwargs) -> int:
        if is_frontend_env_file(path):
            writes.append(data)
            return len(data)
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setenv("DBFOX_ENGINE_TOKEN", "test-token")
    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)
    monkeypatch.setattr(Path, "write_text", fake_write_text)

    runpy.run_path(str(Path(main_module.__file__)), run_name="__dbfox_main_env_test__")

    assert writes == []
