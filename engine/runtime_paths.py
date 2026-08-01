"""Application-owned private runtime paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "DBFox"
PROJECT_DIR = Path(__file__).resolve().parent.parent


def _default_runtime_root() -> Path:
    """Return the platform application-data directory without creating it."""
    override = os.environ.get("DBFOX_RUNTIME_DIR")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_DIR_NAME
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if xdg_data_home:
            return Path(xdg_data_home) / "dbfox"
        return Path.home() / ".local" / "share" / "dbfox"

    raise OSError("DBFox private runtime root is unavailable; set DBFOX_RUNTIME_DIR")


def _chmod_private(path: Path, *, is_dir: bool) -> None:
    """Best-effort owner-only POSIX permissions."""
    try:
        path.chmod(0o700 if is_dir else 0o600)
    except OSError:
        pass


def private_runtime_root() -> Path:
    """Create the single application-owned root for mutable runtime data."""
    root = _default_runtime_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        _chmod_private(root, is_dir=True)
        probe = root / ".write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return root
    except OSError as exc:
        raise OSError(
            "Unable to initialize DBFOX private runtime root; "
            "set DBFOX_RUNTIME_DIR to an application-owned writable directory"
        ) from exc


def private_runtime_dir(name: str) -> Path:
    """Create one validated child directory below the runtime root."""
    if not name or Path(name).name != name:
        raise ValueError("Runtime directory name must be one path component")
    path = private_runtime_root() / name
    path.mkdir(parents=True, exist_ok=True)
    _chmod_private(path, is_dir=True)
    probe = path / ".write_test"
    probe.write_text("", encoding="utf-8")
    probe.unlink(missing_ok=True)
    return path


def private_runtime_file(name: str, filename: str) -> Path:
    """Return a file path below one private runtime directory."""
    return private_runtime_dir(name) / filename


def write_private_bytes(path: Path, data: bytes) -> None:
    """Write bytes and apply owner-only permissions where supported."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_private(path.parent, is_dir=True)
    path.write_bytes(data)
    _chmod_private(path, is_dir=False)


def write_private_text(path: Path, data: str) -> None:
    """Write UTF-8 text using the private file policy."""
    write_private_bytes(path, data.encode("utf-8"))
