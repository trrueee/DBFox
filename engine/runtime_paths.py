from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "DataBox"
PROJECT_DIR = Path(__file__).resolve().parent.parent


def _default_runtime_root() -> Path:
    override = os.environ.get("DATABOX_RUNTIME_DIR")
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
            return Path(xdg_data_home) / "databox"
        return Path.home() / ".local" / "share" / "databox"

    return PROJECT_DIR / ".databox_runtime"


def _chmod_private(path: Path, *, is_dir: bool) -> None:
    try:
        path.chmod(0o700 if is_dir else 0o600)
    except OSError:
        # Windows ACLs are not fully represented by chmod. Best effort is enough here.
        pass


def private_runtime_dir(name: str) -> Path:
    candidates = [_default_runtime_root(), PROJECT_DIR / ".databox_runtime"]
    last_error: OSError | None = None

    for root in candidates:
        try:
            path = root / name
            path.mkdir(parents=True, exist_ok=True)
            _chmod_private(path, is_dir=True)
            probe = path / ".write_test"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise OSError("Unable to create DataBox runtime directory")


def private_runtime_file(name: str, filename: str) -> Path:
    return private_runtime_dir(name) / filename


def write_private_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_private(path.parent, is_dir=True)
    path.write_bytes(data)
    _chmod_private(path, is_dir=False)


def write_private_text(path: Path, data: str) -> None:
    write_private_bytes(path, data.encode("utf-8"))
