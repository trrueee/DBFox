from __future__ import annotations

from pathlib import Path

import pytest

import engine.runtime_paths as runtime_paths
from engine.runtime_paths import private_runtime_dir, private_runtime_root


def test_private_runtime_root_owns_all_runtime_subdirectories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_root))

    assert private_runtime_root() == runtime_root
    assert private_runtime_dir("data") == runtime_root / "data"
    assert private_runtime_dir("config") == runtime_root / "config"
    assert private_runtime_dir("backups") == runtime_root / "backups"


def test_private_runtime_dir_rejects_multi_component_names() -> None:
    with pytest.raises(ValueError):
        private_runtime_dir("data/../outside")


def test_private_runtime_root_fails_closed_when_default_location_is_unwritable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    default_root = tmp_path / "unwritable-runtime"
    original_mkdir = Path.mkdir

    def deny_default_root(self: Path, *args: object, **kwargs: object) -> None:
        if self == default_root:
            raise PermissionError("default runtime location is unavailable")
        original_mkdir(self, *args, **kwargs)

    monkeypatch.delenv("DBFOX_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(runtime_paths, "_default_runtime_root", lambda: default_root)
    monkeypatch.setattr(Path, "mkdir", deny_default_root)

    with pytest.raises(OSError, match="private runtime root"):
        runtime_paths.private_runtime_root()
