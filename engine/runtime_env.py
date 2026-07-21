from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path

from dotenv import dotenv_values


# A repository-local dotenv file is not a credential distribution channel.
# Keep this list deliberately small and limited to non-sensitive operational
# tuning.  Credentials, database URLs, runtime paths, security bypasses and
# provider-specific settings must be injected by the parent process or stored
# in the OS credential vault; a deny-list cannot safely anticipate every
# provider's future secret variable name.
_DOTENV_ALLOWED_CONFIGURATION = frozenset(
    {
        "DBFOX_ENGINE_PORT",
        "DBFOX_DB_POOL_SIZE",
        "DBFOX_DB_MAX_OVERFLOW",
        "DBFOX_DB_POOL_RECYCLE_SECONDS",
        "DBFOX_DB_POOL_TIMEOUT_SECONDS",
        "DBFOX_SQLITE_TIMEOUT_SECONDS",
        "DBFOX_SQL_MAX_POOLS",
        "DBFOX_SQL_MAX_CONNECTIONS",
        "DBFOX_EXPORT_MAX_ROWS",
        "DBFOX_EXPORT_TIMEOUT_MS",
        "DBFOX_AGENT_CHECKPOINT_RETENTION_DAYS",
        "DBFOX_AGENT_CHECKPOINT_MAX_TERMINAL_RUNS",
        "DBFOX_AGENT_CHECKPOINT_MAX_BYTES",
    }
)


def _load_non_secret_env_file(env_file: Path) -> None:
    """Load allowlisted non-secret settings without overriding process env."""
    for name, value in dotenv_values(env_file).items():
        if (
            not name
            or value is None
            or name not in _DOTENV_ALLOWED_CONFIGURATION
            or name in os.environ
        ):
            continue
        os.environ[name] = value


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
    """Load non-secret DBFox configuration before framework imports.

    Private runtime ``config/.env`` and ``config/langsmith.env`` files are
    deliberately not candidates.  They were a plaintext credential channel
    and are retired; callers must use ``CredentialVault`` for credentials.
    """
    if project_env is None:
        project_env = Path(__file__).resolve().parent.parent / ".env"

    candidates: list[Path] = [project_env]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ".env")
    if extra_env_files:
        candidates.extend(extra_env_files)

    loaded: list[Path] = []
    for env_file in _dedupe(candidates):
        if env_file.exists():
            _load_non_secret_env_file(env_file)
            loaded.append(env_file)
    return loaded
