import json
from pathlib import Path

from fastapi.testclient import TestClient

from engine import __version__
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
    response = client.get(
        "/api/v1/health",
        headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert data["version"] == __version__


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


def test_ready_control_message_declares_runtime_protocol(capsys) -> None:
    dev_server_module._emit_engine_ready(18731)

    line = capsys.readouterr().out.strip()
    marker = "DBFOX_ENGINE_READY "
    assert line.startswith(marker)
    payload = json.loads(line[len(marker):])
    assert payload == {
        "port": 18731,
        "protocolVersion": 1,
        "serverInfo": {"name": "dbfox-engine", "version": __version__},
        "capabilities": ["http", "sse", "problem-details"],
    }


def test_optional_startup_stage_cannot_crash_engine(monkeypatch) -> None:
    def broken_control_stream(*_args, **_kwargs) -> None:
        raise OSError(22, "invalid control stream")

    monkeypatch.setattr("builtins.print", broken_control_stream)

    main_module._emit_startup_stage("migrating")


def test_startup_fatal_emits_only_safe_structured_diagnostics(capsys) -> None:
    main_module._emit_startup_fatal(
        "migrating",
        RuntimeError(
            "DBFOX_ALEMBIC_SQLITE_FOREIGN_KEY_VIOLATIONS: "
            "secret-local-database-shape"
        ),
    )

    line = capsys.readouterr().out.strip()
    marker = "DBFOX_ENGINE_FATAL "
    assert line.startswith(marker)
    payload = json.loads(line[len(marker):])
    assert payload["stage"] == "migrating"
    assert payload["code"] == "DBFOX_METADATA_FOREIGN_KEY_VIOLATION"
    assert len(payload["fingerprint"]) == 24
    assert "secret-local-database-shape" not in line


def test_frozen_engine_allows_only_known_desktop_origins(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "is_frozen", True)

    with TestClient(app) as client:
        for origin in ["dbfox-app://localhost"]:
            response = client.get(
                "/api/v1/datasources",
                headers={
                    "Origin": origin,
                    "X-Local-Token": LOCAL_SECURE_TOKEN,
                },
            )

            assert response.status_code != 403
            assert response.headers.get("access-control-allow-origin") == origin

        for rejected_origin in (
            "dbfox-app://attacker.invalid",
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ):
            rejected = client.get(
                "/api/v1/datasources",
                headers={
                    "Origin": rejected_origin,
                    "X-Local-Token": LOCAL_SECURE_TOKEN,
                },
            )
            assert rejected.status_code == 403


def test_frozen_engine_parses_referer_host_instead_of_accepting_prefix_spoof(
    monkeypatch,
) -> None:
    monkeypatch.setattr(main_module, "is_frozen", True)

    with TestClient(app) as client:
        rejected = client.get(
            "/api/v1/health",
            headers={
                "Referer": "http://localhost.attacker.invalid/workspace",
                "X-Local-Token": LOCAL_SECURE_TOKEN,
            },
        )
        electron = client.get(
            "/api/v1/health",
            headers={
                "Referer": "dbfox-app://localhost/workspace",
                "X-Local-Token": LOCAL_SECURE_TOKEN,
            },
        )

    assert electron.status_code != 403
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "FORBIDDEN_ORIGIN"


def test_frozen_health_uses_the_same_origin_and_token_policy(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "is_frozen", True)

    with TestClient(app) as client:
        missing_token = client.get(
            "/api/v1/health",
            headers={"Origin": "dbfox-app://localhost"},
        )
        wrong_token = client.get(
            "/api/v1/health",
            headers={"Origin": "dbfox-app://localhost", "X-Local-Token": "wrong"},
        )
        missing_origin = client.get(
            "/api/v1/health",
            headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
        )
        response = client.get(
            "/api/v1/health",
            headers={
                "Origin": "dbfox-app://localhost",
                "X-Local-Token": LOCAL_SECURE_TOKEN,
            },
        )

    assert missing_token.status_code == 401
    assert wrong_token.status_code == 401
    assert missing_origin.status_code == 403
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_rejects_the_previous_runtime_token(monkeypatch) -> None:
    previous_token = "previous-runtime-token"
    next_token = "next-runtime-token"
    monkeypatch.setattr(main_module, "LOCAL_SECURE_TOKEN", next_token)

    with TestClient(app) as client:
        stale = client.get(
            "/api/v1/health",
            headers={"X-Local-Token": previous_token},
        )
        current = client.get(
            "/api/v1/health",
            headers={"X-Local-Token": next_token},
        )

    assert stale.status_code == 401
    assert current.status_code == 200


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
