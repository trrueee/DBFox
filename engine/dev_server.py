from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ENGINE_DIR = Path(__file__).resolve().parent
ENGINE_HOST = "127.0.0.1"
ENGINE_PORT = 18625

_RELOAD_EXCLUDES = [
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/.codegraph/**",
]


def is_frozen_runtime() -> bool:
    return getattr(sys, "frozen", False)


def default_reload_enabled() -> bool:
    return not is_frozen_runtime()


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

    if reload:
        uvicorn.run(
            "engine.main:app",
            host=ENGINE_HOST,
            port=ENGINE_PORT,
            reload=True,
            reload_dirs=[str(ENGINE_DIR)],
            reload_includes=["*.py"],
            reload_excludes=_RELOAD_EXCLUDES,
        )
        return

    from engine.main import app

    uvicorn.run(app, host=ENGINE_HOST, port=ENGINE_PORT)
