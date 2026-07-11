"""One-time, deliberately limited cleanup for the Foundation v2 runtime.

The reset removes only runtime-derived metadata and a small, fixed family of
local runtime files.  It deliberately has no credential-vault dependency:
vault values are process-global and cannot participate in the metadata SQLite
transaction safely.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import stat
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, make_url

from engine.db import build_metadata_engine
from engine.errors import DBFoxError


FOUNDATION_RUNTIME_VERSION = "2"


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


_SIDECAR_SUFFIXES = ("", "-wal", "-shm", "-journal", ".version")
_BACKUP_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal", ".version")

_AGENT_DELETE_ORDER = (
    "agent_approvals",
    "agent_checkpoints",
    "agent_artifacts",
    "agent_runtime_events",
    "agent_trace_events",
    "agent_runs",
    "agent_session_memories",
    "agent_messages",
    "agent_sessions",
)

_SCHEMA_DELETE_ORDER = (
    "schema_search_docs",
    "workspace_table_scopes",
    "schema_columns",
    "schema_tables",
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
        return path if path.is_absolute() else Path.cwd() / path
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeResetPathError() from exc


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


def _checkpoint_files(
    runtime_root: Path,
    checkpoint_path: Path | None,
    metadata_path: Path,
) -> tuple[Path, ...]:
    if checkpoint_path is None:
        base = _default_checkpoint_path(metadata_path)
    else:
        try:
            base = Path(checkpoint_path).expanduser()
        except (TypeError, ValueError) as exc:
            raise RuntimeResetPathError() from exc
        if not base.is_absolute():
            base = runtime_root / base
    return _sidecar_family(base)


def _backup_family_files(metadata_path: Path) -> tuple[Path, ...]:
    """Return only exact ``<metadata-name>.bak_<digits>`` families."""
    pattern = re.compile(
        rf"^{re.escape(metadata_path.name)}\.bak_(?P<timestamp>[0-9]+)"
        rf"(?:{'|'.join(re.escape(suffix) for suffix in _BACKUP_SIDECAR_SUFFIXES)})?$"
    )
    base_names: set[str] = set()
    try:
        with os.scandir(metadata_path.parent) as entries:
            for entry in entries:
                match = pattern.fullmatch(entry.name)
                if match is not None:
                    base_names.add(f"{metadata_path.name}.bak_{match.group('timestamp')}")
    except OSError as exc:
        raise RuntimeResetPathError() from exc

    files: list[Path] = []
    for base_name in sorted(base_names, key=lambda name: (name.casefold(), name)):
        files.extend(_sidecar_family(metadata_path.with_name(base_name)))
    return tuple(files)


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _dedupe(paths: Iterable[Path]) -> tuple[Path, ...]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = _path_key(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return tuple(result)


def _build_cleanup_plan(
    metadata_url: str,
    runtime_root: Path,
    checkpoint_path: Path | None,
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
            *_checkpoint_files(resolved_root, checkpoint_path, metadata_path),
            resolved_root / "config" / "langsmith.env",
        )
    )
    files = tuple(_validate_candidate(resolved_root, candidate) for candidate in cleanup_candidates)

    # A caller must never be able to re-label the live metadata DB or one of
    # its active sidecars as a checkpoint target.
    metadata_keys = {_path_key(candidate) for candidate in metadata_files}
    if any(_path_key(candidate) in metadata_keys for candidate in files):
        raise RuntimeResetPathError()
    return _CleanupPlan(runtime_root=resolved_root, files=files)


def _remove_external_files(plan: _CleanupPlan) -> None:
    # Revalidate the root as well as every entry to fail closed if a link,
    # junction, reparse point, or directory appears after the complete plan.
    if _require_runtime_root(plan.runtime_root) != plan.runtime_root:
        raise RuntimeResetPathError()
    for candidate in plan.files:
        _validate_candidate(plan.runtime_root, candidate)
        try:
            candidate.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeResetCleanupError() from exc


def _read_marker(connection: Connection) -> bool:
    marker = connection.execute(
        text("SELECT runtime_version FROM foundation_runtime_state WHERE id = 1")
    ).scalar_one_or_none()
    if marker is None:
        return False
    if str(marker) != FOUNDATION_RUNTIME_VERSION:
        raise RuntimeResetStateError()
    return True


def _clear_database_runtime_state(connection: Connection) -> None:
    # Agent children must precede runs, and runs/messages/memory must precede
    # sessions. The names are constants, never user data.
    for table_name in _AGENT_DELETE_ORDER:
        connection.execute(text(f"DELETE FROM {table_name}"))

    # Evaluation data stays, but no retained row may point at a deleted run.
    connection.execute(text("UPDATE agent_eval_case_results SET run_id = NULL WHERE run_id IS NOT NULL"))

    # Workspace scope refers to schema tables; columns can self-reference.
    for table_name in _SCHEMA_DELETE_ORDER:
        connection.execute(text(f"DELETE FROM {table_name}"))

    connection.execute(
        text(
            """
            UPDATE data_sources
            SET password_credential_id = NULL,
                ssh_password_credential_id = NULL,
                ssh_key_passphrase_credential_id = NULL,
                last_test_at = NULL,
                last_test_status = NULL,
                last_test_error = NULL,
                last_test_latency_ms = NULL,
                last_test_readonly = NULL,
                last_test_server_version = NULL,
                last_test_tables_count = NULL,
                last_test_warnings = NULL,
                last_sync_at = NULL,
                last_sync_status = NULL,
                last_sync_error = NULL
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE database_environments
            SET password_credential_id = NULL,
                status = 'created',
                last_health_status = NULL,
                last_health_at = NULL,
                last_error = NULL
            """
        )
    )

    # schema_search_fts is external-content FTS5 without delete triggers.
    connection.execute(text("INSERT INTO schema_search_fts(schema_search_fts) VALUES ('rebuild')"))


def _write_marker(connection: Connection) -> None:
    """Insert the marker as the final successful database statement."""
    connection.execute(
        text(
            """
            INSERT INTO foundation_runtime_state (id, runtime_version, reset_completed_at)
            VALUES (:id, :runtime_version, :reset_completed_at)
            """
        ),
        {
            "id": 1,
            "runtime_version": FOUNDATION_RUNTIME_VERSION,
            "reset_completed_at": datetime.now(UTC),
        },
    )


def reset_legacy_runtime_state(
    metadata_url: str,
    runtime_root: Path,
    *,
    checkpoint_path: Path | None = None,
) -> ResetResult:
    """Perform the Foundation v2 reset once for a local metadata SQLite DB.

    A SQLite ``BEGIN IMMEDIATE`` serializes the first reset. External cleanup
    is fully preflighted and happens before metadata rows change; a cleanup
    failure therefore leaves the transaction unmodified and marker-free.
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
        with engine.connect() as connection:
            try:
                # Deferred SQLite transactions permit two callers to read an
                # absent marker concurrently. Acquire the writer reservation
                # before the re-read so exactly one caller resets.
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                if _read_marker(connection):
                    connection.commit()
                    return ResetResult(False, FOUNDATION_RUNTIME_VERSION)

                plan = _build_cleanup_plan(metadata_url, resolved_root, checkpoint_path)
                _remove_external_files(plan)
                _clear_database_runtime_state(connection)
                _write_marker(connection)
                connection.commit()
                return ResetResult(True, FOUNDATION_RUNTIME_VERSION)
            except Exception:
                if connection.in_transaction():
                    connection.rollback()
                raise
    finally:
        engine.dispose()
