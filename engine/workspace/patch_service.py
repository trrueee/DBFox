"""Bounded atomic write service for the DBFox Project workspace.

This is the write counterpart to :mod:`engine.workspace.read_service`. It does
not depend on Agent RunLoop or Tool Registry, never writes outside the
authorized workspace root, and uses a same-directory temporary file followed
by ``os.replace`` so a completed result is either fully present or not.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from engine.workspace.read_service import WorkspaceReadError, WorkspaceReadService

MAX_WORKSPACE_PATCH_BYTES = 1024 * 1024


class WorkspacePatchError(WorkspaceReadError):
    """The requested workspace write cannot be performed within the boundary."""


class WorkspacePatchConflict(WorkspacePatchError):
    """The current file does not match the expected CAS identity."""


@dataclass(frozen=True, slots=True)
class WorkspacePatchResult:
    relative_path: str
    old_sha256: str | None
    new_sha256: str
    size_bytes: int
    created: bool


class WorkspacePatchService:
    """Apply bounded UTF-8 whole-file patches with CAS and atomic replace."""

    def __init__(self, read_service: WorkspaceReadService) -> None:
        self._read = read_service
        self._root = read_service.root

    @property
    def root(self) -> Path:
        return self._root

    def _resolve_file(self, relative_path: str) -> tuple[str, Path]:
        normalized = WorkspaceReadService._normalize_relative(relative_path)
        if normalized == ".":
            raise WorkspacePatchError("Workspace patch path must identify a file")
        path = self._read.resolve(normalized)
        if path.exists() and path.is_dir():
            raise WorkspacePatchError("Workspace patch target is a directory")
        return normalized, path

    def apply_patch(
        self,
        relative_path: str,
        content: str,
        expected_sha256: str | None = None,
    ) -> WorkspacePatchResult:
        normalized, path = self._resolve_file(relative_path)
        data = content.encode("utf-8")
        if len(data) > MAX_WORKSPACE_PATCH_BYTES:
            raise WorkspacePatchError("Workspace patch exceeds the byte limit")

        old_sha256: str | None = None
        created = False
        if path.exists():
            if not path.is_file():
                raise WorkspacePatchError("Workspace patch target is not a file")
            old_data = path.read_bytes()
            old_sha256 = hashlib.sha256(old_data).hexdigest()
        else:
            created = True

        expected = (expected_sha256 or "").strip().lower()
        if expected:
            if old_sha256 != expected:
                raise WorkspacePatchConflict(
                    "Workspace file changed before the patch could be applied"
                )
        elif old_sha256 is not None:
            raise WorkspacePatchConflict(
                "Workspace patch requires the current file SHA-256"
            )

        new_sha256 = hashlib.sha256(data).hexdigest()
        parent = path.parent
        if not parent.exists() or not parent.is_dir():
            raise WorkspacePatchError("Workspace patch directory does not exist")

        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".dbfox-tmp",
            dir=parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as temp_file:
                temp_file.write(data)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

        return WorkspacePatchResult(
            relative_path=normalized,
            old_sha256=old_sha256,
            new_sha256=new_sha256,
            size_bytes=len(data),
            created=created,
        )

    def reconcile(
        self,
        relative_path: str,
        content: str,
        expected_sha256: str | None = None,
    ) -> tuple[str, WorkspacePatchResult | None]:
        """Infer one write outcome from current filesystem state only.

        Returns ``("succeeded", result)`` when the file already matches the
        proposed content, ``("not_applied", None)`` when it still matches the
        expected old SHA, and ``("unknown", None)`` when the user or another
        process changed the file in the interim.
        """

        normalized, path = self._resolve_file(relative_path)
        data = content.encode("utf-8")
        if len(data) > MAX_WORKSPACE_PATCH_BYTES:
            raise WorkspacePatchError("Workspace patch exceeds the byte limit")
        new_sha256 = hashlib.sha256(data).hexdigest()

        if path.exists() and path.is_file():
            current_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            if current_sha256 == new_sha256:
                return "succeeded", WorkspacePatchResult(
                    relative_path=normalized,
                    old_sha256=(expected_sha256 or "").strip().lower() or None,
                    new_sha256=new_sha256,
                    size_bytes=len(data),
                    created=False,
                )
            expected = (expected_sha256 or "").strip().lower()
            if expected and current_sha256 == expected:
                return "not_applied", None
            return "unknown", None

        return "not_applied", None
