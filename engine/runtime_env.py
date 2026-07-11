from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path

from dotenv import dotenv_values


_CREDENTIAL_ENV_PREFIXES = ("LANGCHAIN_", "LANGSMITH_")
_CREDENTIAL_ENV_MARKERS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSPHRASE",
)


def _is_credential_environment_variable(name: str) -> bool:
    """Return whether an environment variable name can carry a secret.

    Runtime ``.env`` files are configuration inputs only.  Product credentials
    are intentionally resolved at their provider boundary from
    :class:`CredentialVault`; this guard prevents a dotenv file from quietly
    recreating a plaintext credential fallback.
    """
    normalized = name.upper()
    return normalized.startswith(_CREDENTIAL_ENV_PREFIXES) or any(
        marker in normalized for marker in _CREDENTIAL_ENV_MARKERS
    )


def _load_non_secret_env_file(env_file: Path) -> None:
    """Load non-secret values from one dotenv file without overriding process env."""
    for name, value in dotenv_values(env_file).items():
        if (
            not name
            or value is None
            or _is_credential_environment_variable(name)
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
