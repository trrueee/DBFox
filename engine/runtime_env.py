from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

from dotenv import load_dotenv

from engine.runtime_paths import private_runtime_file


def _private_env_candidates() -> list[Path]:
    try:
        return [
            private_runtime_file("config", "langsmith.env"),
            private_runtime_file("config", ".env"),
        ]
    except OSError:
        return []


def _dedupe(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def load_runtime_env(
    *,
    project_env: Path | None = None,
    extra_env_files: Iterable[Path] | None = None,
) -> list[Path]:
    """Load DBFox runtime env files before LangChain is imported."""
    if project_env is None:
        project_env = Path(__file__).resolve().parent.parent / ".env"

    candidates: list[Path] = [project_env]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ".env")
    candidates.extend(_private_env_candidates())
    if extra_env_files:
        candidates.extend(extra_env_files)

    loaded: list[Path] = []
    for env_file in _dedupe(candidates):
        if env_file.exists():
            load_dotenv(env_file, override=False)
            loaded.append(env_file)
    return loaded
