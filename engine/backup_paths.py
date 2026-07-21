"""Owned backup-path validation and file-integrity helpers."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.errors import DBFoxError
from engine.models import DEFAULT_PROJECT_ID, DataSource
from engine.runtime_paths import private_runtime_dir

_BACKUP_ROOT_NAME = "backups"


class BackupError(DBFoxError):
    def __init__(self, message: str, code: str = "BACKUP_FAILED") -> None:
        super().__init__(message, code=code)


def backup_operation_error() -> BackupError:
    return BackupError(
        fixed_error_message(FixedErrorCode.BACKUP_OPERATION_FAILED),
        code=FixedErrorCode.BACKUP_OPERATION_FAILED.value,
    )


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "backup"


def _is_link_or_reparse(file_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(file_stat.st_mode):
        return True
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(file_stat, "st_file_attributes", 0)
    return bool(reparse_point and file_attributes & reparse_point)


def absolute_lexical_path(path: Path) -> Path:
    try:
        expanded = path.expanduser()
        absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise backup_operation_error() from exc
    if not absolute.anchor:
        raise backup_operation_error()
    for index, part in enumerate(absolute.parts):
        if index == 0 and part == absolute.anchor:
            continue
        if part in {"", ".", ".."}:
            raise backup_operation_error()
        if os.name == "nt" and (part.endswith((".", " ")) or ":" in part):
            raise backup_operation_error()
    return absolute


def require_private_directory(path: Path) -> Path:
    absolute = absolute_lexical_path(path)
    current = Path(absolute.anchor)
    try:
        root_stat = current.lstat()
    except OSError as exc:
        raise backup_operation_error() from exc
    if _is_link_or_reparse(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
        raise backup_operation_error()
    for part in absolute.parts[1:]:
        current = current / part
        try:
            component_stat = current.lstat()
        except OSError as exc:
            raise backup_operation_error() from exc
        if _is_link_or_reparse(component_stat) or not stat.S_ISDIR(component_stat.st_mode):
            raise backup_operation_error()
    return absolute


def _make_private_directory(path: Path) -> None:
    try:
        path.chmod(0o700)
    except OSError:
        pass


def backup_root() -> Path:
    return require_private_directory(private_runtime_dir(_BACKUP_ROOT_NAME))


def backup_relative_path(ds: DataSource, backup_id: str) -> PurePosixPath:
    project_id = _safe_filename(str(ds.project_id or DEFAULT_PROJECT_ID))
    datasource_id = _safe_filename(str(ds.id))
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}_{_safe_filename(str(ds.database_name))}_{backup_id[:8]}.sql"
    return PurePosixPath(project_id, datasource_id, filename)


def parse_backup_relative_path(value: object) -> PurePosixPath | None:
    raw = str(value or "").strip()
    if not raw or "\\" in raw or "\x00" in raw or ":" in raw:
        return None
    try:
        relative = PurePosixPath(raw)
    except (TypeError, ValueError):
        return None
    if relative.is_absolute() or raw != relative.as_posix() or len(relative.parts) != 3:
        return None
    if relative.suffix.lower() != ".sql":
        return None
    if any(part in {"", ".", ".."} or _safe_filename(part) != part for part in relative.parts):
        return None
    return relative


def safe_backup_record_path(value: object) -> str | None:
    relative = parse_backup_relative_path(value)
    return relative.as_posix() if relative is not None else None


def _ensure_backup_parent(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise backup_operation_error() from exc
        try:
            component_stat = current.lstat()
        except OSError as exc:
            raise backup_operation_error() from exc
        if _is_link_or_reparse(component_stat) or not stat.S_ISDIR(component_stat.st_mode):
            raise backup_operation_error()
        _make_private_directory(current)
    return current


def new_owned_backup_path(relative: PurePosixPath) -> Path:
    parent = _ensure_backup_parent(backup_root(), relative)
    path = parent / relative.name
    try:
        existing = path.lstat()
    except FileNotFoundError:
        return path
    except OSError as exc:
        raise backup_operation_error() from exc
    if _is_link_or_reparse(existing) or not stat.S_ISREG(existing.st_mode):
        raise backup_operation_error()
    raise backup_operation_error()


def existing_owned_backup_path(relative: PurePosixPath) -> Path:
    path = backup_root().joinpath(*relative.parts)
    require_private_directory(path.parent)
    try:
        file_stat = path.lstat()
    except OSError as exc:
        raise backup_operation_error() from exc
    if _is_link_or_reparse(file_stat) or not stat.S_ISREG(file_stat.st_mode):
        raise backup_operation_error()
    return path


def backup_path(ds: DataSource, backup_id: str) -> Path:
    return new_owned_backup_path(backup_relative_path(ds, backup_id))


def regular_file_size(path: Path) -> int:
    require_private_directory(path.parent)
    try:
        file_stat = path.lstat()
    except OSError as exc:
        raise backup_operation_error() from exc
    if _is_link_or_reparse(file_stat) or not stat.S_ISREG(file_stat.st_mode):
        raise backup_operation_error()
    return int(file_stat.st_size)


def open_existing_regular_file(path: Path, flags: int) -> int:
    require_private_directory(path.parent)
    try:
        before = path.lstat()
    except OSError as exc:
        raise backup_operation_error() from exc
    if _is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
        raise backup_operation_error()
    try:
        descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise backup_operation_error() from exc
    try:
        after = os.fstat(descriptor)
        if not stat.S_ISREG(after.st_mode) or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise backup_operation_error()
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = open_existing_regular_file(path, os.O_RDONLY)
    with os.fdopen(descriptor, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_regular_file_if_owned(path: Path) -> None:
    try:
        require_private_directory(path.parent)
        file_stat = path.lstat()
    except (BackupError, FileNotFoundError, OSError):
        return
    if _is_link_or_reparse(file_stat) or not stat.S_ISREG(file_stat.st_mode):
        return
    try:
        path.unlink()
    except OSError:
        pass
