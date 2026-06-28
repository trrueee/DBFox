from pathlib import Path

from fastapi.testclient import TestClient

from engine.db import Base, engine as db_engine
# Ensure all ORM tables exist in the test database so that app-level
# TestClient requests (e.g. /api/v1/datasources) do not fail with a
# missing-table error.
Base.metadata.create_all(bind=db_engine)

from engine.main import LOCAL_SECURE_TOKEN, app
import engine.main as main_module
from engine.dev_server import _RELOAD_EXCLUDES
from engine.dev_server import bind_engine_socket
from engine.main import _write_frontend_env_file_if_owned

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
    assert data["version"] == "1.0.1"


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


def test_dev_frontend_env_writer_skips_user_owned_env_file(tmp_path: Path) -> None:
    """A .env.local containing custom user keys must never be overwritten."""
    env_file = tmp_path / ".env.local"
    user_owned_content = "VITE_CUSTOM_FLAG=1\n"
    env_file.write_text(user_owned_content, encoding="utf-8")

    _write_frontend_env_file_if_owned(env_file, "test-token")

    # File is untouched because it contains non-DBFox keys.
    assert env_file.read_text("utf-8") == user_owned_content


def test_dev_frontend_env_writer_updates_dbfox_owned_env_file(tmp_path: Path) -> None:
    """A DBFox-owned .env.local is refreshed when the token changes."""
    env_file = tmp_path / ".env.local"
    env_file.write_text(_frontend_env_content_with("old-token"), encoding="utf-8")

    _write_frontend_env_file_if_owned(env_file, "new-token")

    content = env_file.read_text("utf-8")
    assert "new-token" in content
    assert "old-token" not in content


def test_dev_frontend_env_writer_creates_missing_env_file(tmp_path: Path) -> None:
    """A missing .env.local is created fresh with the current token."""
    env_file = tmp_path / ".env.local"
    assert not env_file.exists()

    _write_frontend_env_file_if_owned(env_file, "fresh-token")

    content = env_file.read_text("utf-8")
    assert "VITE_LOCAL_ENGINE_PORT" in content
    assert "fresh-token" in content


def _frontend_env_content_with(token: str) -> str:
    """Helper mirroring engine.main._frontend_env_content layout."""
    return f"VITE_LOCAL_ENGINE_PORT=18625\nVITE_LOCAL_ENGINE_TOKEN={token}\n"
