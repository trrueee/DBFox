from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

MAX_WORKSPACE_FILE_BYTES = 1024 * 1024
MAX_WORKSPACE_DIR_ENTRIES = 600
_SKIPPED_DIR_NAMES = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", "target",
    "dist", "build", ".next", ".pytest_cache", ".mypy_cache", ".ruff_cache",
})


class WorkspaceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WorkspaceEntry:
    name: str
    relative_path: str
    is_dir: bool


@dataclass(frozen=True, slots=True)
class WorkspaceFile:
    relative_path: str
    content: str
    size_bytes: int
    sha256: str
    truncated: bool


class WorkspaceService:
    def __init__(self, root: str | Path) -> None:
        try:
            self.root = Path(root).expanduser().resolve(strict=True)
        except OSError as exc:
            raise WorkspaceError("Workspace root is unavailable") from exc
        if not self.root.is_dir():
            raise WorkspaceError("Workspace root is not a directory")

    @property
    def root_digest(self) -> str:
        return hashlib.sha256(str(self.root).encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def normalize(relative_path: str) -> str:
        value = str(relative_path or "").strip().replace("\\", "/")
        if not value:
            return "."
        if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
            raise WorkspaceError("Workspace path must be relative")
        parts: list[str] = []
        for part in value.split("/"):
            if part in {"", "."}:
                continue
            if part == "..":
                raise WorkspaceError("Workspace path must not contain '..'")
            parts.append(part)
        return "/".join(parts) if parts else "."

    def resolve(self, relative_path: str) -> Path:
        normalized = self.normalize(relative_path)
        candidate = (self.root / normalized).resolve(strict=False)
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise WorkspaceError("Workspace path escapes the authorized root")
        return candidate

    def list_directory(self, relative_path: str = "") -> tuple[WorkspaceEntry, ...]:
        directory = self.resolve(relative_path)
        if not directory.exists() or not directory.is_dir():
            raise WorkspaceError("Workspace directory does not exist")
        entries: list[WorkspaceEntry] = []
        with os.scandir(directory) as iterator:
            for item in iterator:
                try:
                    is_dir = item.is_dir(follow_symlinks=False) or (
                        item.is_symlink() and Path(item.path).resolve(strict=True).is_dir()
                    )
                except OSError:
                    continue
                if is_dir and item.name in _SKIPPED_DIR_NAMES:
                    continue
                parent = self.normalize(relative_path)
                child = item.name if parent == "." else f"{parent}/{item.name}"
                entries.append(WorkspaceEntry(item.name, child, is_dir))
        entries.sort(key=lambda entry: (not entry.is_dir, entry.name.casefold()))
        return tuple(entries[:MAX_WORKSPACE_DIR_ENTRIES])

    def read_text_file(self, relative_path: str) -> WorkspaceFile:
        path = self.resolve(relative_path)
        if not path.exists() or not path.is_file():
            raise WorkspaceError("Workspace file does not exist")
        try:
            size = path.stat().st_size
            data = path.read_bytes()[:MAX_WORKSPACE_FILE_BYTES]
        except OSError as exc:
            raise WorkspaceError("Workspace file cannot be read") from exc
        if any(byte == 0 for byte in data[:8192]):
            raise WorkspaceError("Workspace binary file cannot be read as text")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError("Workspace file is not UTF-8 text") from exc
        return WorkspaceFile(
            relative_path=self.normalize(relative_path),
            content=content,
            size_bytes=size,
            sha256=hashlib.sha256(data).hexdigest(),
            truncated=size > MAX_WORKSPACE_FILE_BYTES,
        )
