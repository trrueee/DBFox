"""Bounded read-only Workspace resource service.

This is P5A's backend counterpart to the Tauri-host file viewer. It never
depends on Agent RunLoop, Tool Registry or Prompt assembly, never writes, and
never escapes the approved workspace root.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

MAX_WORKSPACE_FILE_BYTES = 1024 * 1024
MAX_WORKSPACE_DIR_ENTRIES = 600
_SKIPPED_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "target",
        "dist",
        "build",
        ".next",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".turbo",
    }
)


@dataclass(frozen=True, slots=True)
class WorkspaceDirEntry:
    name: str
    relative_path: str
    is_dir: bool


@dataclass(frozen=True, slots=True)
class WorkspaceFileSnapshot:
    relative_path: str
    content: str
    size_bytes: int
    sha256: str
    truncated: bool = False


class WorkspaceReadError(ValueError):
    """The requested workspace resource cannot be read within the boundary."""


class WorkspaceReadService:
    """Authorized reads from one canonical project workspace root."""

    def __init__(self, root: str | Path) -> None:
        root_path = Path(root).expanduser()
        try:
            self._root = root_path.resolve(strict=True)
        except OSError as exc:
            raise WorkspaceReadError(f"Workspace root is unavailable: {root}") from exc
        if not self._root.is_dir():
            raise WorkspaceReadError(f"Workspace root is not a directory: {root}")

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, relative_path: str) -> Path:
        """Return the contained filesystem path or raise WorkspaceReadError."""

        normalized = self._normalize_relative(relative_path)
        candidate = (self._root / normalized).resolve(strict=False)
        if candidate != self._root and not candidate.is_relative_to(self._root):
            raise WorkspaceReadError("Workspace path escapes the authorized root")
        return candidate

    def list_directory(
        self,
        relative_path: str = "",
        *,
        limit: int = MAX_WORKSPACE_DIR_ENTRIES,
    ) -> tuple[WorkspaceDirEntry, ...]:
        if limit < 1 or limit > MAX_WORKSPACE_DIR_ENTRIES:
            raise WorkspaceReadError("Workspace directory entry limit is invalid")
        directory = self.resolve(relative_path)
        if not directory.exists() or not directory.is_dir():
            raise WorkspaceReadError(f"Workspace directory does not exist: {relative_path}")

        entries: list[WorkspaceDirEntry] = []
        with os.scandir(directory) as iterator:
            for item in iterator:
                name = item.name
                try:
                    is_dir = item.is_dir(follow_symlinks=False) or (
                        item.is_symlink() and Path(item.path).resolve(strict=True).is_dir()
                    )
                except OSError:
                    continue
                if is_dir and name in _SKIPPED_DIR_NAMES:
                    continue
                child_relative = self._join_relative(relative_path, name)
                entries.append(
                    WorkspaceDirEntry(
                        name=name,
                        relative_path=child_relative,
                        is_dir=is_dir,
                    )
                )
        entries.sort(key=lambda entry: (not entry.is_dir, entry.name.casefold()))
        return tuple(entries[:limit])

    def read_text_file(
        self,
        relative_path: str,
        *,
        max_bytes: int = MAX_WORKSPACE_FILE_BYTES,
    ) -> WorkspaceFileSnapshot:
        if max_bytes < 1 or max_bytes > MAX_WORKSPACE_FILE_BYTES:
            raise WorkspaceReadError("Workspace file byte limit is invalid")
        path = self.resolve(relative_path)
        try:
            if not path.exists() or not path.is_file():
                raise WorkspaceReadError(f"Workspace file does not exist: {relative_path}")
            size = path.stat().st_size
            truncated = size > max_bytes
            if truncated:
                data = path.read_bytes()[:max_bytes]
            else:
                data = path.read_bytes()
        except WorkspaceReadError:
            raise
        except OSError as exc:
            raise WorkspaceReadError(f"Workspace file cannot be read: {relative_path}") from exc

        if any(byte == 0 for byte in data[:8192]):
            raise WorkspaceReadError("Workspace binary file cannot be read as text")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceReadError("Workspace file is not UTF-8 text") from exc
        digest = hashlib.sha256(data).hexdigest()
        return WorkspaceFileSnapshot(
            relative_path=self._normalize_relative(relative_path),
            content=content,
            size_bytes=size,
            sha256=digest,
            truncated=truncated,
        )

    @staticmethod
    def _normalize_relative(relative_path: str) -> str:
        value = str(relative_path or "").strip().replace("\\", "/")
        if not value:
            return "."
        if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
            raise WorkspaceReadError("Workspace path must be relative")
        parts: list[str] = []
        for part in value.split("/"):
            if part in {"", "."}:
                continue
            if part == "..":
                raise WorkspaceReadError("Workspace path must not contain '..'")
            parts.append(part)
        return "/".join(parts) if parts else "."

    @staticmethod
    def _join_relative(parent: str, name: str) -> str:
        normalized_parent = WorkspaceReadService._normalize_relative(parent)
        return name if normalized_parent == "." else f"{normalized_parent}/{name}"
