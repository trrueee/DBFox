"""One-time destructive cleanup for the Foundation v2 runtime.

The reset has two durable phases.  The metadata transaction first clears the
legacy database state and records a *pending* marker; only then are fixed,
local runtime artifacts removed.  A failed external cleanup therefore remains
pending and is retried safely on the next startup instead of leaving a
marker-free, partially reset installation.

The module deliberately has no credential-vault dependency: vault values are
process-global and cannot participate in the metadata SQLite transaction
safely.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
from typing import Iterable

from sqlalchemy.engine import Connection, Engine, make_url

from engine.db import build_metadata_engine
from engine.errors import DBFoxError
from engine.runtime_paths import PROJECT_DIR
from engine.security.runtime_reset_database import (
    clear_database_runtime_state,
    compact_metadata_after_reset,
    mark_cleanup_completed,
    read_marker,
    write_pending_marker,
)


# Version 2 was written by the first, incomplete reset implementation. Version
# 3 introduced the durable cleanup protocol and strict privacy-preserving
# allowlist. Version 4 retires the fixed legacy local AES key file that prior
# releases wrote under the private runtime. Only these known predecessors may
# be upgraded; any other value remains fail-closed.
FOUNDATION_RUNTIME_VERSION = "4"
_UPGRADABLE_LEGACY_RUNTIME_VERSIONS = frozenset({"2", "3"})


class RuntimeResetPathError(DBFoxError):
    """A reset target is outside the private runtime or unsafe to use."""

    def __init__(self) -> None:
        super().__init__("Runtime reset rejected an unsafe cleanup path.", code="RUNTIME_RESET_PATH")


class RuntimeResetCleanupError(DBFoxError):
    """A validated external runtime artifact could not be removed."""

    def __init__(self) -> None:
        super().__init__("Runtime reset could not remove a cleanup artifact.", code="RUNTIME_RESET_CLEANUP")


class RuntimeResetStateError(DBFoxError):
    """The singleton marker has an unsupported value and cannot be overwritten."""

    def __init__(self) -> None:
        super().__init__("Runtime reset found an unsupported reset state.", code="RUNTIME_RESET_STATE")


@dataclass(frozen=True)
class ResetResult:
    reset_performed: bool
    runtime_version: str


# Kept as a narrow source-compatible name for callers that adopted the first
# draft before the public ResetResult contract was finalized.
RuntimeResetResult = ResetResult


@dataclass(frozen=True)
class _CleanupPlan:
    runtime_root: Path
    files: tuple[Path, ...]
    protected_files: tuple[Path, ...]
    # Directories are removed after files, in deepest-first order.  They are
    # deliberately explicit instead of using a recursive remover so the same
    # pinned-handle / dir-fd containment rules apply to every deletion.
    directories: tuple[Path, ...] = ()


_SIDECAR_SUFFIXES = ("", "-wal", "-shm", "-journal", ".version")
_BACKUP_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal", ".version")

_RESET_MARKER_MISSING = "missing"
_RESET_MARKER_PENDING = "pending"
_RESET_MARKER_COMPLETED = "completed"
_RESET_MARKER_LEGACY = "legacy"

_MAX_MANAGED_BACKUP_FILES = 10_000
_MAX_MANAGED_BACKUP_DEPTH = 5
_O_DIRECTORY = int(getattr(os, "O_DIRECTORY", 0))
_O_NOFOLLOW = int(getattr(os, "O_NOFOLLOW", 0))

# This was the exact source-checkout fallback used before private runtime
# storage became mandatory.  Do not infer an arbitrary checkout subdirectory
# from configuration or data records: only this fixed historical location is
# eligible for retirement.
_LEGACY_PROJECT_RUNTIME_DIR_NAME = ".dbfox_runtime"
_LEGACY_PROJECT_RUNTIME_TOP_LEVEL_DIRS = frozenset(
    {
        "auth",
        "backups",
        "config",
        "data",
        "logs",
        "memory",
        "secrets",
        "tests",
    }
)
_MAX_LEGACY_PROJECT_RUNTIME_FILES = 10_000
_MAX_LEGACY_PROJECT_RUNTIME_DEPTH = 8

_RESET_DELETE_ORDER = (
    # Leaf records first.  These can contain prompts, SQL, result rows, or
    # serialized Agent state and are never allowed to cross the Foundation
    # boundary.
    "confirmation_tokens",
    "agent_evidence",
    "agent_question_requests",
    "agent_observations",
    "agent_approvals",
    "agent_events",
    "agent_task_plans",
    "agent_checkpoints",
    "agent_artifacts",
    "agent_tool_invocations",
    "agent_turns",
    "agent_runtime_events",
    "agent_trace_events",
    "agent_eval_case_results",
    "workspace_table_scopes",
    "query_history_search_docs",

    # Runs must precede messages: the run FK uses SET NULL on a message but
    # reset deletes both, and the explicit order is stable across SQLite.
    "agent_runs",
    "agent_session_inputs",
    "agent_session_memories",
    "agent_messages",
    "agent_sessions",

    "agent_eval_runs",
    "agent_golden_tasks",

    # Schema/search state is reconstructed from the datasource after users
    # explicitly re-enrol credentials.
    "schema_search_docs",
    "schema_columns",
    "schema_tables",

    "query_history",

    # These records may contain source SQL, prompts, responses, backup paths,
    # user business terminology, or other legacy state.  The Foundation reset
    # intentionally preserves none of them.
    "llm_logs",
    "golden_sqls",
    "reusable_sqls",
    "semantic_aliases",
    "domain_tag_rules",
    "backup_records",
    "table_design_drafts",
)


def _is_link_or_reparse(file_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(file_stat.st_mode):
        return True
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(file_stat, "st_file_attributes", 0)
    return bool(reparse_point and file_attributes & reparse_point)


def _absolute_lexical_path(path: Path) -> Path:
    """Return an absolute lexical path without resolving links."""
    try:
        absolute_path = path if path.is_absolute() else Path.cwd() / path
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeResetPathError() from exc
    _reject_windows_path_aliases(absolute_path)
    return absolute_path


def _reject_windows_path_aliases(path: Path) -> None:
    """Reject Win32 spellings that can alias another path or an ADS stream.

    The reset has no user-facing path input, so accepting names such as
    ``state.db.`` or ``state.db::$DATA`` buys no compatibility and makes a
    string-based path guard unsound on NTFS.  Handle identity checks below are
    the final authority; this early rule keeps unsafe metadata URLs out of the
    cleanup plan altogether.
    """
    if os.name != "nt":
        return
    for index, part in enumerate(path.parts):
        if index == 0 and part == path.anchor:
            continue
        if part in {"", ".", ".."}:
            continue
        if part.endswith((".", " ")) or ":" in part:
            raise RuntimeResetPathError()


def _validate_existing_components(path: Path, *, require_all: bool) -> None:
    """Reject a symlink/junction/reparse point in any existing component."""
    absolute_path = _absolute_lexical_path(path)
    if not absolute_path.anchor:
        raise RuntimeResetPathError()

    current = Path(absolute_path.anchor)
    try:
        anchor_stat = current.lstat()
    except OSError as exc:
        raise RuntimeResetPathError() from exc
    if _is_link_or_reparse(anchor_stat):
        raise RuntimeResetPathError()

    parts = absolute_path.parts
    for index, part in enumerate(parts[1:], start=1):
        if part in {"", "."}:
            continue
        if part == "..":
            raise RuntimeResetPathError()
        current = current / part
        try:
            component_stat = current.lstat()
        except FileNotFoundError as exc:
            if require_all:
                raise RuntimeResetPathError() from exc
            return
        except OSError as exc:
            raise RuntimeResetPathError() from exc
        if _is_link_or_reparse(component_stat):
            raise RuntimeResetPathError()
        if index < len(parts) - 1 and not stat.S_ISDIR(component_stat.st_mode):
            raise RuntimeResetPathError()


def _require_runtime_root(runtime_root: Path) -> Path:
    try:
        raw_root = _absolute_lexical_path(Path(runtime_root).expanduser())
        _validate_existing_components(raw_root, require_all=True)
        root_stat = raw_root.lstat()
    except RuntimeResetPathError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeResetPathError() from exc
    if _is_link_or_reparse(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
        raise RuntimeResetPathError()
    try:
        return raw_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RuntimeResetPathError() from exc


def _require_inside_runtime_root(runtime_root: Path, candidate: Path) -> Path:
    raw_candidate = _absolute_lexical_path(candidate)
    try:
        # Check the spelling first, so a lexical ``..`` cannot be used to
        # disguise a target that happens to resolve back under the root.
        relative_parts = raw_candidate.relative_to(runtime_root).parts
        if ".." in relative_parts:
            raise RuntimeResetPathError()
        resolved_candidate = raw_candidate.resolve(strict=False)
        resolved_candidate.relative_to(runtime_root)
    except RuntimeResetPathError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeResetPathError() from exc
    return raw_candidate


def _validate_candidate(
    runtime_root: Path,
    candidate: Path,
    *,
    require_existing: bool = False,
) -> Path:
    """Validate one exact target without following a link during deletion."""
    raw_candidate = _require_inside_runtime_root(runtime_root, candidate)
    _validate_existing_components(raw_candidate, require_all=False)
    try:
        candidate_stat = raw_candidate.lstat()
    except FileNotFoundError as exc:
        if require_existing:
            raise RuntimeResetPathError() from exc
        return raw_candidate
    except OSError as exc:
        raise RuntimeResetPathError() from exc
    if _is_link_or_reparse(candidate_stat) or not stat.S_ISREG(candidate_stat.st_mode):
        raise RuntimeResetPathError()
    return raw_candidate


def _validate_directory_candidate(
    runtime_root: Path,
    candidate: Path,
    *,
    require_existing: bool = False,
) -> Path:
    """Validate one exact directory without following links during removal."""
    raw_candidate = _require_inside_runtime_root(runtime_root, candidate)
    _validate_existing_components(raw_candidate, require_all=False)
    try:
        candidate_stat = raw_candidate.lstat()
    except FileNotFoundError as exc:
        if require_existing:
            raise RuntimeResetPathError() from exc
        return raw_candidate
    except OSError as exc:
        raise RuntimeResetPathError() from exc
    if _is_link_or_reparse(candidate_stat) or not stat.S_ISDIR(candidate_stat.st_mode):
        raise RuntimeResetPathError()
    return raw_candidate


def _metadata_path(metadata_url: str, runtime_root: Path) -> Path:
    try:
        metadata = make_url(metadata_url)
    except Exception as exc:
        raise RuntimeResetPathError() from exc
    if (
        metadata.get_backend_name() != "sqlite"
        or not metadata.database
        or metadata.username is not None
        or metadata.password is not None
        or metadata.host is not None
        or metadata.port is not None
        or metadata.query
    ):
        raise RuntimeResetPathError()

    database_name = metadata.database
    if database_name == ":memory:" or database_name.casefold().startswith("file:"):
        raise RuntimeResetPathError()
    try:
        raw_path = Path(database_name)
    except (TypeError, ValueError) as exc:
        raise RuntimeResetPathError() from exc
    if not raw_path.is_absolute():
        raise RuntimeResetPathError()
    return _validate_candidate(runtime_root, raw_path, require_existing=True)


def _sidecar_family(base: Path) -> tuple[Path, ...]:
    return tuple(base.with_name(f"{base.name}{suffix}") for suffix in _SIDECAR_SUFFIXES)


def _default_checkpoint_path(metadata_path: Path) -> Path:
    """Keep checkpoints beside the validated metadata file, never DB_PATH."""
    return metadata_path.with_name("dbfox_agent_core_checkpoints.sqlite")


def _checkpoint_files(metadata_path: Path) -> tuple[Path, ...]:
    """Return the only checkpoint family owned by the Foundation runtime.

    A reset must never accept a caller-selected file and relabel it as a
    checkpoint.  The location is deterministic from the validated metadata
    database, which also makes an interrupted cleanup safely resumable.
    """
    return _sidecar_family(_default_checkpoint_path(metadata_path))


def _backup_family_files(metadata_path: Path) -> tuple[Path, ...]:
    """Return only exact ``<metadata-name>.bak_<digits>`` families."""
    pattern = re.compile(
        rf"^(?P<base>{re.escape(metadata_path.name)}\.bak_(?P<timestamp>[0-9]+))"
        rf"(?:{'|'.join(re.escape(suffix) for suffix in _BACKUP_SIDECAR_SUFFIXES)})?$",
        flags=re.IGNORECASE if os.name == "nt" else 0,
    )
    base_names: set[str] = set()
    try:
        with os.scandir(metadata_path.parent) as entries:
            for entry in entries:
                match = pattern.fullmatch(entry.name)
                if match is not None:
                    # Keep the directory entry's real spelling.  NTFS is
                    # case-insensitive, while a case-sensitive filesystem
                    # must only touch the exact metadata family.
                    base_names.add(match.group("base"))
    except OSError as exc:
        raise RuntimeResetPathError() from exc

    files: list[Path] = []
    for base_name in sorted(base_names, key=lambda name: (name.casefold(), name)):
        files.extend(_sidecar_family(metadata_path.with_name(base_name)))
    return tuple(files)


def _managed_backup_files(runtime_root: Path) -> tuple[Path, ...]:
    """Enumerate only regular files inside DBFox's owned backup directory.

    Backup records are deleted by the reset, so their stored paths cannot be
    trusted as cleanup instructions.  The runtime-owned ``backups`` directory
    is the sole authority.  A link, special file, excessive depth, or
    unreasonable file count fails closed rather than widening cleanup scope.
    Empty directories are harmless and deliberately left behind.
    """
    backup_root = runtime_root / "backups"
    try:
        root_stat = backup_root.lstat()
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise RuntimeResetPathError() from exc
    if _is_link_or_reparse(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
        raise RuntimeResetPathError()

    files: list[Path] = []

    def visit(directory: Path, depth: int) -> None:
        if depth > _MAX_MANAGED_BACKUP_DEPTH:
            raise RuntimeResetPathError()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    candidate = directory / entry.name
                    try:
                        candidate_stat = candidate.lstat()
                    except OSError as exc:
                        raise RuntimeResetPathError() from exc
                    if _is_link_or_reparse(candidate_stat):
                        raise RuntimeResetPathError()
                    if stat.S_ISDIR(candidate_stat.st_mode):
                        visit(candidate, depth + 1)
                    elif stat.S_ISREG(candidate_stat.st_mode):
                        files.append(candidate)
                        if len(files) > _MAX_MANAGED_BACKUP_FILES:
                            raise RuntimeResetPathError()
                    else:
                        raise RuntimeResetPathError()
        except RuntimeResetPathError:
            raise
        except OSError as exc:
            raise RuntimeResetPathError() from exc

    visit(backup_root, 0)
    return tuple(files)


def _dedupe(paths: Iterable[Path]) -> tuple[Path, ...]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(os.path.normpath(str(path)))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return tuple(result)


def _build_cleanup_plan(
    metadata_url: str,
    runtime_root: Path,
) -> _CleanupPlan:
    resolved_root = _require_runtime_root(runtime_root)
    metadata_path = _metadata_path(metadata_url, resolved_root)

    # Validate the live metadata file and its exact sidecars, but never delete
    # them.  A SQLite connection may own its WAL/SHM while this reset runs.
    metadata_files = tuple(
        _validate_candidate(resolved_root, candidate, require_existing=candidate == metadata_path)
        for candidate in _sidecar_family(metadata_path)
    )
    cleanup_candidates = _dedupe(
        (
            *_backup_family_files(metadata_path),
            *_checkpoint_files(metadata_path),
            *_managed_backup_files(resolved_root),
            resolved_root / "config" / "langsmith.env",
            resolved_root / "config" / ".env",
            # This is the sole former local credential-encryption key path.
            # It is fixed beneath the validated private runtime; no user or
            # metadata-provided path can influence its deletion.
            resolved_root / "secrets" / ".secret_key",
        )
    )
    files = tuple(_validate_candidate(resolved_root, candidate) for candidate in cleanup_candidates)

    # String comparison is intentionally not used for the live sidecar guard:
    # NTFS aliases (case, trailing dots, alternate data streams, short names)
    # can identify the same file through distinct spellings.  The secure
    # remover compares pinned file identities immediately before deletion.
    return _CleanupPlan(
        runtime_root=resolved_root,
        files=files,
        protected_files=metadata_files,
    )


def _directory_trees_overlap(first: Path, second: Path) -> bool:
    """Return whether two existing directory trees share an ancestor.

    ``samefile`` compares filesystem identities instead of relying on Win32
    spelling, case, or short-name aliases.  Both paths have already passed the
    no-link validation performed by ``_require_runtime_root``.
    """
    for child, ancestor in ((first, second), (second, first)):
        current = child
        while True:
            try:
                if os.path.samefile(current, ancestor):
                    return True
            except OSError as exc:
                raise RuntimeResetPathError() from exc
            parent = current.parent
            if parent == current:
                break
            current = parent
    return False


def _build_legacy_project_runtime_cleanup_plan(
    active_runtime_root: Path,
) -> _CleanupPlan | None:
    """Preflight the fixed source-checkout runtime tree before any deletion.

    The legacy directory is deliberately not caller-selected.  Its historical
    top-level layout is allowlisted, while nested content is limited to normal
    directories and regular files.  A link, special file, unexpected top-level
    name, or unreasonable tree fails closed before the first file is removed.
    """
    project_root = _require_runtime_root(PROJECT_DIR)
    legacy_root = project_root / _LEGACY_PROJECT_RUNTIME_DIR_NAME
    try:
        legacy_root.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeResetPathError() from exc
    legacy_root = _validate_directory_candidate(
        project_root,
        legacy_root,
        require_existing=True,
    )

    active_root = _require_runtime_root(active_runtime_root)
    if _directory_trees_overlap(legacy_root, active_root):
        raise RuntimeResetPathError()

    files: list[Path] = []
    directories: list[Path] = [legacy_root]

    def visit(directory: Path, depth: int) -> None:
        if depth > _MAX_LEGACY_PROJECT_RUNTIME_DEPTH:
            raise RuntimeResetPathError()
        try:
            with os.scandir(directory) as entries:
                for entry in sorted(entries, key=lambda item: (item.name.casefold(), item.name)):
                    candidate = directory / entry.name
                    try:
                        candidate_stat = candidate.lstat()
                    except OSError as exc:
                        raise RuntimeResetPathError() from exc
                    if _is_link_or_reparse(candidate_stat):
                        raise RuntimeResetPathError()
                    if depth == 0 and (
                        entry.name not in _LEGACY_PROJECT_RUNTIME_TOP_LEVEL_DIRS
                        or not stat.S_ISDIR(candidate_stat.st_mode)
                    ):
                        raise RuntimeResetPathError()
                    if stat.S_ISDIR(candidate_stat.st_mode):
                        if depth >= _MAX_LEGACY_PROJECT_RUNTIME_DEPTH:
                            raise RuntimeResetPathError()
                        directories.append(candidate)
                        visit(candidate, depth + 1)
                    elif stat.S_ISREG(candidate_stat.st_mode):
                        files.append(candidate)
                        if len(files) > _MAX_LEGACY_PROJECT_RUNTIME_FILES:
                            raise RuntimeResetPathError()
                    else:
                        raise RuntimeResetPathError()
        except RuntimeResetPathError:
            raise
        except OSError as exc:
            raise RuntimeResetPathError() from exc

    visit(legacy_root, 0)
    validated_files = tuple(
        _validate_candidate(project_root, candidate)
        for candidate in files
    )
    validated_directories = tuple(
        _validate_directory_candidate(project_root, candidate, require_existing=True)
        for candidate in sorted(
            directories,
            key=lambda candidate: (
                len(candidate.relative_to(project_root).parts),
                str(candidate).casefold(),
                str(candidate),
            ),
            reverse=True,
        )
    )
    return _CleanupPlan(
        runtime_root=project_root,
        files=validated_files,
        protected_files=(),
        directories=validated_directories,
    )


def _cleanup_relative_parts(runtime_root: Path, candidate: Path) -> tuple[str, ...]:
    try:
        relative = candidate.relative_to(runtime_root)
    except ValueError as exc:
        raise RuntimeResetPathError() from exc
    parts = relative.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise RuntimeResetPathError()
    return tuple(parts)


def _remove_external_files_posix(plan: _CleanupPlan) -> None:
    """Delete through pinned directory descriptors on POSIX platforms.

    Each lookup is relative to an already-open parent directory and uses
    ``O_NOFOLLOW``.  Replacing a path component after planning therefore
    cannot redirect deletion outside the private runtime tree.
    """
    required_flags = _O_DIRECTORY | _O_NOFOLLOW
    if (
        not required_flags
        or os.open not in os.supports_dir_fd
        or os.unlink not in os.supports_dir_fd
        or os.rmdir not in os.supports_dir_fd
    ):
        raise RuntimeResetPathError()

    directory_flags = os.O_RDONLY | required_flags
    try:
        root_fd = os.open(plan.runtime_root.anchor, directory_flags)
    except OSError as exc:
        raise RuntimeResetPathError() from exc
    try:
        for part in plan.runtime_root.parts[1:]:
            try:
                child_fd = os.open(part, directory_flags, dir_fd=root_fd)
            except OSError as exc:
                raise RuntimeResetPathError() from exc
            os.close(root_fd)
            root_fd = child_fd

        if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
            raise RuntimeResetPathError()

        protected_identities: set[tuple[int, int]] = set()
        for protected in plan.protected_files:
            identity = _posix_file_identity(root_fd, plan.runtime_root, protected)
            if identity is not None:
                protected_identities.add(identity)

        for candidate in plan.files:
            _remove_posix_file(
                root_fd,
                plan.runtime_root,
                candidate,
                protected_identities,
            )
        for directory in plan.directories:
            _remove_posix_directory(root_fd, plan.runtime_root, directory)
    finally:
        os.close(root_fd)


def _posix_open_parent(root_fd: int, runtime_root: Path, candidate: Path) -> tuple[int, str]:
    parts = _cleanup_relative_parts(runtime_root, candidate)
    parent_fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            try:
                child_fd = os.open(
                    part,
                    os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW,
                    dir_fd=parent_fd,
                )
            except FileNotFoundError:
                os.close(parent_fd)
                return -1, parts[-1]
            except OSError as exc:
                raise RuntimeResetPathError() from exc
            os.close(parent_fd)
            parent_fd = child_fd
        return parent_fd, parts[-1]
    except BaseException:
        if parent_fd >= 0:
            os.close(parent_fd)
        raise


def _posix_file_identity(root_fd: int, runtime_root: Path, candidate: Path) -> tuple[int, int] | None:
    parent_fd, leaf = _posix_open_parent(root_fd, runtime_root, candidate)
    if parent_fd < 0:
        return None
    try:
        try:
            file_fd = os.open(leaf, os.O_RDONLY | _O_NOFOLLOW, dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise RuntimeResetPathError() from exc
        try:
            file_stat = os.fstat(file_fd)
        finally:
            os.close(file_fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise RuntimeResetPathError()
        return file_stat.st_dev, file_stat.st_ino
    finally:
        os.close(parent_fd)


def _remove_posix_file(
    root_fd: int,
    runtime_root: Path,
    candidate: Path,
    protected_identities: set[tuple[int, int]],
) -> None:
    parent_fd, leaf = _posix_open_parent(root_fd, runtime_root, candidate)
    if parent_fd < 0:
        return
    try:
        try:
            file_stat = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RuntimeResetPathError() from exc
        if not stat.S_ISREG(file_stat.st_mode):
            raise RuntimeResetPathError()
        if (file_stat.st_dev, file_stat.st_ino) in protected_identities:
            raise RuntimeResetPathError()
        try:
            os.unlink(leaf, dir_fd=parent_fd)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RuntimeResetCleanupError() from exc
    finally:
        os.close(parent_fd)


def _remove_posix_directory(root_fd: int, runtime_root: Path, directory: Path) -> None:
    """Remove one preflighted empty directory through its pinned parent fd."""
    parent_fd, leaf = _posix_open_parent(root_fd, runtime_root, directory)
    if parent_fd < 0:
        return
    try:
        try:
            directory_stat = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RuntimeResetPathError() from exc
        if not stat.S_ISDIR(directory_stat.st_mode):
            raise RuntimeResetPathError()
        try:
            os.rmdir(leaf, dir_fd=parent_fd)
        except FileNotFoundError:
            return
        except OSError as exc:
            # A concurrent writer or a newly introduced link/file leaves the
            # directory non-empty; never widen the cleanup scope to recover.
            raise RuntimeResetCleanupError() from exc
    finally:
        os.close(parent_fd)


def _remove_external_files_windows(plan: _CleanupPlan) -> None:
    """Delete fixed runtime files by handle, never by a mutable Win32 path."""
    import ctypes
    import ntpath
    from ctypes import wintypes

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    class _FileDispositionInformation(ctypes.Structure):
        _fields_ = [("delete_file", wintypes.BOOL)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ByHandleFileInformation)]
    get_information.restype = wintypes.BOOL
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get_final_path.restype = wintypes.DWORD
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    set_information.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    delete_access = 0x00010000
    read_attributes = 0x00000080
    share_read_write = 0x00000003
    open_existing_disposition = 3
    file_attribute_reparse_point = 0x00000400
    file_flag_backup_semantics = 0x02000000
    file_flag_open_reparse_point = 0x00200000
    file_disposition_information = 4
    file_name_normalized = 0
    error_file_not_found = 2
    error_path_not_found = 3
    invalid_handle_value = ctypes.c_void_p(-1).value

    def close(pinned: tuple[int, tuple[int, int], str, int] | None) -> None:
        if pinned is not None:
            close_handle(pinned[0])

    def final_path(handle: int) -> str:
        required = get_final_path(handle, None, 0, file_name_normalized)
        if not required:
            raise RuntimeResetPathError()
        buffer = ctypes.create_unicode_buffer(required + 1)
        copied = get_final_path(handle, buffer, len(buffer), file_name_normalized)
        if not copied or copied >= len(buffer):
            raise RuntimeResetPathError()
        return ntpath.normcase(ntpath.normpath(buffer.value))

    def is_inside(root_path: str, child_path: str) -> bool:
        try:
            return ntpath.commonpath([root_path, child_path]) == root_path
        except ValueError:
            return False

    def open_existing_handle(
        path: Path,
        *,
        directory: bool,
        delete: bool,
    ) -> tuple[int, tuple[int, int], str, int] | None:
        flags = file_flag_open_reparse_point
        if directory:
            flags |= file_flag_backup_semantics
        handle = create_file(
            str(path),
            read_attributes | (delete_access if delete else 0),
            share_read_write,
            None,
            open_existing_disposition,
            flags,
            None,
        )
        if handle == invalid_handle_value:
            error = ctypes.get_last_error()
            if error in {error_file_not_found, error_path_not_found}:
                return None
            raise RuntimeResetCleanupError() from OSError(error, "CreateFileW failed")
        info = _ByHandleFileInformation()
        if not get_information(handle, ctypes.byref(info)):
            error = ctypes.get_last_error()
            close_handle(handle)
            raise RuntimeResetCleanupError() from OSError(error, "GetFileInformationByHandle failed")
        attributes = int(info.dwFileAttributes)
        # Win32 attributes are authoritative here; opening a directory needs
        # BACKUP_SEMANTICS, while a reparse point must never be followed.
        if attributes & file_attribute_reparse_point or (directory != bool(attributes & 0x10)):
            close_handle(handle)
            raise RuntimeResetPathError()
        identity = (
            int(info.dwVolumeSerialNumber),
            (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow),
        )
        try:
            resolved_path = final_path(handle)
        except BaseException:
            close_handle(handle)
            raise
        return handle, identity, resolved_path, attributes

    root = open_existing_handle(plan.runtime_root, directory=True, delete=False)
    if root is None:
        raise RuntimeResetPathError()
    root_path = root[2]
    pinned: list[tuple[int, tuple[int, int], str, int]] = [root]

    def open_under_root(
        candidate: Path,
        *,
        required: bool,
        delete: bool,
        directory: bool,
    ) -> tuple[
        tuple[int, tuple[int, int], str, int] | None,
        tuple[tuple[int, tuple[int, int], str, int], ...],
    ]:
        parts = _cleanup_relative_parts(plan.runtime_root, candidate)
        current = plan.runtime_root
        local_parents: list[tuple[int, tuple[int, int], str, int]] = []
        try:
            for part in parts[:-1]:
                current = current / part
                parent = open_existing_handle(current, directory=True, delete=False)
                if parent is None:
                    if required:
                        raise RuntimeResetPathError()
                    for opened_parent in reversed(local_parents):
                        close(opened_parent)
                    return None, ()
                if not is_inside(root_path, parent[2]):
                    close(parent)
                    raise RuntimeResetPathError()
                local_parents.append(parent)
            target = open_existing_handle(candidate, directory=directory, delete=delete)
            if target is None:
                if required:
                    raise RuntimeResetPathError()
                for opened_parent in reversed(local_parents):
                    close(opened_parent)
                return None, ()
            if not is_inside(root_path, target[2]):
                close(target)
                raise RuntimeResetPathError()
            return target, tuple(local_parents)
        except BaseException:
            for parent in reversed(local_parents):
                close(parent)
            raise

    try:
        protected_identities: set[tuple[int, int]] = set()
        for protected in plan.protected_files:
            protected_handle, protected_parents = open_under_root(
                protected,
                required=protected == plan.protected_files[0],
                delete=False,
                directory=False,
            )
            if protected_handle is not None:
                protected_identities.add(protected_handle[1])
                pinned.extend(protected_parents)
                pinned.append(protected_handle)

        for candidate in plan.files:
            target, target_parents = open_under_root(
                candidate,
                required=False,
                delete=True,
                directory=False,
            )
            if target is None:
                continue
            try:
                if target[1] in protected_identities:
                    raise RuntimeResetPathError()
                disposition = _FileDispositionInformation(True)
                if not set_information(
                    target[0],
                    file_disposition_information,
                    ctypes.byref(disposition),
                    ctypes.sizeof(disposition),
                ):
                    error = ctypes.get_last_error()
                    raise RuntimeResetCleanupError() from OSError(
                        error,
                        "SetFileInformationByHandle failed",
                    )
            finally:
                close(target)
                for parent in reversed(target_parents):
                    close(parent)
        for directory in plan.directories:
            target, target_parents = open_under_root(
                directory,
                required=False,
                delete=True,
                directory=True,
            )
            if target is None:
                continue
            try:
                disposition = _FileDispositionInformation(True)
                if not set_information(
                    target[0],
                    file_disposition_information,
                    ctypes.byref(disposition),
                    ctypes.sizeof(disposition),
                ):
                    error = ctypes.get_last_error()
                    raise RuntimeResetCleanupError() from OSError(
                        error,
                        "SetFileInformationByHandle directory delete failed",
                    )
            finally:
                close(target)
                for parent in reversed(target_parents):
                    close(parent)
    finally:
        for handle in reversed(pinned):
            close(handle)


def _remove_external_files(plan: _CleanupPlan) -> None:
    # The initial plan check is a fail-closed early rejection.  Actual removal
    # below repeats containment and uses pinned OS handles, so no mutable path
    # is ever passed to unlink on Windows.
    if _require_runtime_root(plan.runtime_root) != plan.runtime_root:
        raise RuntimeResetPathError()
    if os.name == "nt":
        _remove_external_files_windows(plan)
    else:
        _remove_external_files_posix(plan)


def _read_marker(connection: Connection) -> str:
    return read_marker(
        connection,
        runtime_version=FOUNDATION_RUNTIME_VERSION,
        upgradable_versions=_UPGRADABLE_LEGACY_RUNTIME_VERSIONS,
        state_error=RuntimeResetStateError,
    )


def _clear_database_runtime_state(connection: Connection) -> None:
    clear_database_runtime_state(connection, delete_order=_RESET_DELETE_ORDER)


def _write_pending_marker(connection: Connection) -> None:
    """Durably record that database reset completed but cleanup is pending."""
    write_pending_marker(
        connection,
        runtime_version=FOUNDATION_RUNTIME_VERSION,
    )


def _mark_cleanup_completed(connection: Connection) -> None:
    mark_cleanup_completed(
        connection,
        runtime_version=FOUNDATION_RUNTIME_VERSION,
    )


def _compact_metadata_after_reset(engine: Engine) -> None:
    """Rewrite the metadata file and truncate WAL before completing reset.

    ``secure_delete`` is enabled on every metadata connection, but historical
    plaintext can already be on SQLite free pages or in the WAL.  A one-time
    VACUUM copies only live pages into a new file; checkpointing then removes
    the old WAL.  A failure intentionally leaves the durable marker pending so
    the next startup retries rather than claiming a completed privacy reset.
    """
    compact_metadata_after_reset(engine, cleanup_error=RuntimeResetCleanupError)


def reset_legacy_runtime_state(
    metadata_url: str,
    runtime_root: Path,
) -> ResetResult:
    """Perform the current Foundation reset once for a local metadata SQLite DB.

    The first transaction deletes database state and commits a pending marker.
    A second, writer-serialized transaction removes only fixed runtime files
    and changes that marker to completed.  If cleanup fails or the process
    crashes, the durable pending marker makes the next startup retry cleanup
    without reintroducing a marker-free partial reset.
    """
    resolved_root = _require_runtime_root(runtime_root)
    _metadata_path(metadata_url, resolved_root)
    try:
        engine: Engine = build_metadata_engine(metadata_url)
    except Exception as exc:
        raise RuntimeResetPathError() from exc

    try:
        if engine.dialect.name != "sqlite":
            raise RuntimeResetPathError()

        # Preflight all fixed artifacts before any metadata row changes.  The
        # handle-based remover repeats these checks at deletion time.
        plan = _build_cleanup_plan(metadata_url, resolved_root)

        with engine.connect() as connection:
            try:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                state = _read_marker(connection)
                if state == _RESET_MARKER_COMPLETED:
                    connection.commit()
                    return ResetResult(False, FOUNDATION_RUNTIME_VERSION)
                if state in {_RESET_MARKER_MISSING, _RESET_MARKER_LEGACY}:
                    _clear_database_runtime_state(connection)
                    _write_pending_marker(connection)
                connection.commit()
            except Exception:
                if connection.in_transaction():
                    connection.rollback()
                raise

        with engine.connect() as connection:
            try:
                # Keep the SQLite writer reservation through cleanup and the
                # completion transition. Another startup may observe pending
                # between phases, but only one can own this final phase.
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                state = _read_marker(connection)
                if state == _RESET_MARKER_COMPLETED:
                    connection.commit()
                    return ResetResult(False, FOUNDATION_RUNTIME_VERSION)
                if state != _RESET_MARKER_PENDING:
                    raise RuntimeResetStateError()
                _remove_external_files(plan)
                connection.commit()
            except Exception:
                if connection.in_transaction():
                    connection.rollback()
                raise

        _compact_metadata_after_reset(engine)

        with engine.connect() as connection:
            try:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                state = _read_marker(connection)
                if state == _RESET_MARKER_COMPLETED:
                    connection.commit()
                    return ResetResult(False, FOUNDATION_RUNTIME_VERSION)
                if state != _RESET_MARKER_PENDING:
                    raise RuntimeResetStateError()
                _mark_cleanup_completed(connection)
                connection.commit()
                return ResetResult(True, FOUNDATION_RUNTIME_VERSION)
            except Exception:
                if connection.in_transaction():
                    connection.rollback()
                raise
    finally:
        engine.dispose()


def retire_legacy_source_runtime(runtime_root: Path) -> bool:
    """Delete the exact pre-Foundation source-mode metadata artifact family.

    This is intentionally narrower than the normal reset: it is used only
    after the application has successfully initialized its new private
    runtime.  It never follows stored database paths or scans arbitrary source
    directories; the only permitted names are the historical metadata file,
    its SQLite/checkpoint sidecars, and its exact timestamped metadata backups.
    """
    resolved_root = _require_runtime_root(runtime_root)
    legacy_metadata = resolved_root / "dbfox_local.db"
    cleanup_candidates = _dedupe(
        (
            *_sidecar_family(legacy_metadata),
            *_checkpoint_files(legacy_metadata),
            *_backup_family_files(legacy_metadata),
        )
    )
    files = tuple(_validate_candidate(resolved_root, candidate) for candidate in cleanup_candidates)
    if not any(candidate.exists() for candidate in files):
        return False
    _remove_external_files(
        _CleanupPlan(
            runtime_root=resolved_root,
            files=files,
            protected_files=(),
        )
    )
    return True


def retire_legacy_project_runtime_dir(active_runtime_root: Path) -> bool:
    """Retire the fixed pre-Foundation checkout-local runtime directory.

    This is intentionally independent from ``retire_legacy_source_runtime``:
    the latter owns only a narrow SQLite artifact family, while this function
    owns the single historical ``PROJECT_DIR/.dbfox_runtime`` tree.  It is safe
    to call repeatedly after the new private runtime has been initialized and
    verified.  If the old tree is active, linked, malformed, or changes during
    retirement, cleanup fails closed rather than following or deleting a
    caller-controlled path.
    """
    plan = _build_legacy_project_runtime_cleanup_plan(active_runtime_root)
    if plan is None:
        return False
    _remove_external_files(plan)
    return True
