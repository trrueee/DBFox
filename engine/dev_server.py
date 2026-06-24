from __future__ import annotations

import os
import sys
import json
import socket
from pathlib import Path

import uvicorn

ENGINE_DIR = Path(__file__).resolve().parent
ENGINE_HOST = "127.0.0.1"
ENGINE_PORT = int(os.environ.get("DBFOX_ENGINE_PORT", "18625"))

_RELOAD_EXCLUDES = [
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/.codegraph/**",
]


def is_frozen_runtime() -> bool:
    return getattr(sys, "frozen", False)


def default_reload_enabled() -> bool:
    return not is_frozen_runtime()


def bind_engine_socket(port: int) -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((ENGINE_HOST, port))
    sock.listen(socket.SOMAXCONN)
    return sock, int(sock.getsockname()[1])


def _emit_engine_ready(port: int) -> None:
    print(f"DBFOX_ENGINE_READY {json.dumps({'port': port}, separators=(',', ':'))}", flush=True)


def _write_frontend_env_for_dev(port: int | None = None) -> None:
    """Write desktop/.env.local so Vite picks up the engine token before starting.

    Must happen BEFORE uvicorn starts (not inside lifespan), otherwise Vite may
    start before the backend writes the file and read a stale/empty token.
    """
    from pathlib import Path as _Path

    env_file = _Path(__file__).resolve().parent.parent / "desktop" / ".env.local"
    existing = ""
    if env_file.exists():
        existing = env_file.read_text("utf-8")
    need_write = True
    if existing:
        # Check whether the file was written by us (only VITE_* keys, no custom content)
        from engine.main import _is_dbfox_owned_frontend_env
        if not _is_dbfox_owned_frontend_env(existing):
            need_write = False  # user has custom content, don't overwrite
        else:
            from engine.main import LOCAL_SECURE_TOKEN, _frontend_env_content
            expected = _frontend_env_content(LOCAL_SECURE_TOKEN, port=port)
            if existing.strip() == expected.strip():
                need_write = False  # already up to date

    if need_write:
        from engine.main import LOCAL_SECURE_TOKEN, _frontend_env_content
        env_file.write_text(_frontend_env_content(LOCAL_SECURE_TOKEN, port=port), "utf-8")


def run_engine_server(*, reload: bool | None = None) -> None:
    """Start the local DBFox engine. Dev mode watches engine/*.py for changes."""
    # When built with --noconsole (Windows GUI subsystem), sys.stdout / sys.stderr
    # are None and uvicorn's logging layer crashes.  Give them a harmless fallback.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    if reload is None:
        reload = default_reload_enabled()
    port = int(os.environ.get("DBFOX_ENGINE_PORT", str(ENGINE_PORT)))

    if reload:
        # Write frontend env file BEFORE uvicorn starts so Vite always reads
        # a valid token — even during a cold start race.
        if not is_frozen_runtime():
            _write_frontend_env_for_dev(port)
        uvicorn.run(
            "engine.main:app",
            host=ENGINE_HOST,
            port=port,
            reload=True,
            reload_dirs=[str(ENGINE_DIR)],
            reload_includes=["*.py"],
            reload_excludes=_RELOAD_EXCLUDES,
        )
        return

    from engine.main import app

    sock, actual_port = bind_engine_socket(port)
    os.environ["DBFOX_ENGINE_PORT"] = str(actual_port)
    if not is_frozen_runtime():
        _write_frontend_env_for_dev(actual_port)
    _emit_engine_ready(actual_port)

    config = uvicorn.Config(app, host=ENGINE_HOST, port=actual_port)
    server = uvicorn.Server(config)
    server.run(sockets=[sock])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DBFox local engine dev server")
    parser.add_argument(
        "--reload",
        action=argparse.BooleanOptionalAction,
        default=default_reload_enabled(),
        help="Watch engine/*.py and auto-restart on save (default: on in dev)",
    )
    args = parser.parse_args()
    run_engine_server(reload=args.reload)
