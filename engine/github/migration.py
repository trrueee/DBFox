"""R5.2 one-way cutover from historical Core GitHub rows to DLC-owned SQLite.

This module is an explicitly temporary compatibility boundary.  The Alembic
revision invokes it once during upgrade, and the remaining static GitHub
surface uses the same target store until R5.3 deletes Core GitHub wiring.
Historical rows are never updated or deleted.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

_BINDING_COLUMNS = (
    "id",
    "project_id",
    "owner",
    "repository",
    "ref_name",
    "resolved_revision",
    "default_branch",
    "description",
    "created_at",
    "updated_at",
)


class GithubDataMigrationError(RuntimeError):
    """Fail-closed migration or target-store integrity error."""


@dataclass(frozen=True)
class GithubDataMigrationResult:
    source_row_count: int
    source_fingerprint: str
    target_changed: bool


@dataclass(frozen=True)
class GithubBindingRecord:
    """Core-facing value read from the authoritative DLC target store."""

    id: str
    project_id: str
    owner: str
    repository: str
    ref_name: str
    resolved_revision: str
    default_branch: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


def _metadata_database_path(bind: Engine | Connection) -> Path:
    engine = bind.engine if isinstance(bind, Connection) else bind
    if engine.dialect.name != "sqlite" or not engine.url.database:
        raise GithubDataMigrationError(
            "GitHub DLC migration requires a file-backed SQLite database"
        )
    return Path(engine.url.database).resolve()


def github_dlc_data_path(bind: Engine | Connection) -> Path:
    """Resolve the product DLC data path while keeping isolated DB tests isolated."""
    metadata_path = _metadata_database_path(bind)
    from engine.db import DB_PATH
    from engine.runtime_paths import private_runtime_dir

    if metadata_path == DB_PATH.resolve():
        storage_root = private_runtime_dir("dlcs")
    else:
        storage_root = metadata_path.parent / "dlcs"
        storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root / "data" / "dbfox.github"


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise GithubDataMigrationError(
                "Historical GitHub timestamp is invalid"
            ) from exc
    raise GithubDataMigrationError("Historical GitHub timestamp is missing or invalid")


def _canonical_row(
    row: RowMapping | sqlite3.Row | dict[str, Any]
) -> dict[str, str | None]:
    values = dict(row)
    return {
        "id": str(values["id"]),
        "project_id": str(values["project_id"]),
        "owner": str(values["owner"]),
        "repository": str(values["repository"]),
        "ref_name": str(values["ref_name"]),
        "resolved_revision": str(values["resolved_revision"]),
        "default_branch": (
            str(values["default_branch"])
            if values.get("default_branch") is not None
            else None
        ),
        "description": (
            str(values["description"])
            if values.get("description") is not None
            else None
        ),
        "created_at": _timestamp(values["created_at"]),
        "updated_at": _timestamp(values["updated_at"]),
    }


def _fingerprint(rows: Sequence[dict[str, str | None]]) -> str:
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_legacy_rows(source: Session | Connection) -> list[dict[str, str | None]]:
    rows = source.execute(
        text(
            """
            SELECT id, project_id, owner, repository, ref_name,
                   resolved_revision, default_branch, description,
                   created_at, updated_at
              FROM github_repository_bindings
             ORDER BY id
            """
        )
    ).mappings()
    return [_canonical_row(row) for row in rows]


class TransitionalGithubBindingStore:
    """Temporary Core adapter over the DLC-owned database; removed in R5.3."""

    def __init__(self, data_path: Path) -> None:
        data_path.mkdir(parents=True, exist_ok=True)
        self.database_path = data_path / "state.sqlite3"
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("PRAGMA secure_delete = ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS repository_bindings (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    ref_name TEXT NOT NULL,
                    resolved_revision TEXT NOT NULL,
                    default_branch TEXT,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, owner, repository, ref_name)
                );
                CREATE INDEX IF NOT EXISTS ix_repository_bindings_project
                    ON repository_bindings(project_id, created_at, id);
                CREATE TABLE IF NOT EXISTS legacy_core_import_rows (
                    binding_id TEXT PRIMARY KEY
                );
                PRAGMA user_version = 1;
                """
            )

    @staticmethod
    def _binding(row: sqlite3.Row) -> GithubBindingRecord:
        values = _canonical_row(row)
        return GithubBindingRecord(
            id=str(values["id"]),
            project_id=str(values["project_id"]),
            owner=str(values["owner"]),
            repository=str(values["repository"]),
            ref_name=str(values["ref_name"]),
            resolved_revision=str(values["resolved_revision"]),
            default_branch=values["default_branch"],
            description=values["description"],
            created_at=datetime.fromisoformat(str(values["created_at"])),
            updated_at=datetime.fromisoformat(str(values["updated_at"])),
        )

    def sync_legacy_rows(self, rows: Sequence[dict[str, str | None]]) -> bool:
        """Synchronize only identities owned by an uncompleted Alembic import."""
        changed = False
        source_ids = {str(row["id"]) for row in rows}
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                staged_ids = {
                    str(row["binding_id"])
                    for row in connection.execute(
                        "SELECT binding_id FROM legacy_core_import_rows"
                    ).fetchall()
                }
                for stale_id in sorted(staged_ids - source_ids):
                    connection.execute(
                        "DELETE FROM repository_bindings WHERE id = ?", (stale_id,)
                    )
                    connection.execute(
                        "DELETE FROM legacy_core_import_rows WHERE binding_id = ?",
                        (stale_id,),
                    )
                    changed = True
                for row in rows:
                    existing = connection.execute(
                        """
                        SELECT id, project_id, owner, repository, ref_name,
                               resolved_revision, default_branch, description,
                               created_at, updated_at
                          FROM repository_bindings
                         WHERE id = ?
                        """,
                        (row["id"],),
                    ).fetchone()
                    is_staged = str(row["id"]) in staged_ids
                    if (
                        existing is not None
                        and not is_staged
                        and _canonical_row(existing) != row
                    ):
                        raise GithubDataMigrationError(
                            "DLC target contains a conflicting non-migration GitHub binding identity"
                        )
                    if existing is None:
                        connection.execute(
                            """
                            INSERT INTO repository_bindings (
                                id, project_id, owner, repository, ref_name,
                                resolved_revision, default_branch, description,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            tuple(row[column] for column in _BINDING_COLUMNS),
                        )
                        changed = True
                    elif _canonical_row(existing) != row:
                        connection.execute(
                            """
                            UPDATE repository_bindings
                               SET project_id = ?, owner = ?, repository = ?, ref_name = ?,
                                   resolved_revision = ?, default_branch = ?, description = ?,
                                   created_at = ?, updated_at = ?
                             WHERE id = ?
                            """,
                            (
                                row["project_id"],
                                row["owner"],
                                row["repository"],
                                row["ref_name"],
                                row["resolved_revision"],
                                row["default_branch"],
                                row["description"],
                                row["created_at"],
                                row["updated_at"],
                                row["id"],
                            ),
                        )
                        changed = True
                    connection.execute(
                        "INSERT OR IGNORE INTO legacy_core_import_rows (binding_id) VALUES (?)",
                        (row["id"],),
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return changed

    def validate_legacy_rows(self, rows: Sequence[dict[str, str | None]]) -> None:
        with self._connect() as connection:
            for row in rows:
                target = connection.execute(
                    """
                    SELECT id, project_id, owner, repository, ref_name,
                           resolved_revision, default_branch, description,
                           created_at, updated_at
                      FROM repository_bindings
                     WHERE id = ?
                    """,
                    (row["id"],),
                ).fetchone()
                if target is None or _canonical_row(target) != row:
                    raise GithubDataMigrationError(
                        "DLC target validation failed before GitHub cutover"
                    )

    def list_bindings(self, project_id: str) -> list[GithubBindingRecord]:
        if not project_id:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, owner, repository, ref_name,
                       resolved_revision, default_branch, description,
                       created_at, updated_at
                  FROM repository_bindings
                 WHERE project_id = ?
                 ORDER BY created_at, id
                """,
                (project_id,),
            ).fetchall()
        return [self._binding(row) for row in rows]

    def get_binding(self, binding_id: str) -> GithubBindingRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, owner, repository, ref_name,
                       resolved_revision, default_branch, description,
                       created_at, updated_at
                  FROM repository_bindings
                 WHERE id = ?
                """,
                (binding_id,),
            ).fetchone()
        return self._binding(row) if row is not None else None

    def create_binding(self, binding: GithubBindingRecord) -> None:
        row = {
            "id": binding.id,
            "project_id": binding.project_id,
            "owner": binding.owner,
            "repository": binding.repository,
            "ref_name": binding.ref_name,
            "resolved_revision": binding.resolved_revision,
            "default_branch": binding.default_branch,
            "description": binding.description,
            "created_at": binding.created_at.isoformat(),
            "updated_at": binding.updated_at.isoformat(),
        }
        with self._connect() as connection, connection:
            connection.execute(
                """
                INSERT INTO repository_bindings (
                    id, project_id, owner, repository, ref_name,
                    resolved_revision, default_branch, description,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(row[column] for column in _BINDING_COLUMNS),
            )

    def update_binding(self, binding: GithubBindingRecord) -> None:
        with self._connect() as connection, connection:
            cursor = connection.execute(
                """
                UPDATE repository_bindings
                   SET ref_name = ?, resolved_revision = ?, default_branch = ?,
                       description = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    binding.ref_name,
                    binding.resolved_revision,
                    binding.default_branch,
                    binding.description,
                    binding.updated_at.isoformat(),
                    binding.id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(binding.id)

    def delete_binding(self, project_id: str, binding_id: str) -> bool:
        with self._connect() as connection, connection:
            cursor = connection.execute(
                "DELETE FROM repository_bindings WHERE id = ? AND project_id = ?",
                (binding_id, project_id),
            )
        return cursor.rowcount == 1


def migrate_legacy_github_data(
    source: Session | Connection,
    *,
    data_path: Path | None = None,
) -> GithubDataMigrationResult:
    """Commit and verify the target before Alembic records the cutover revision."""
    bind = source.get_bind() if isinstance(source, Session) else source
    store = TransitionalGithubBindingStore(data_path or github_dlc_data_path(bind))
    rows = _load_legacy_rows(source)
    fingerprint = _fingerprint(rows)
    try:
        changed = store.sync_legacy_rows(rows)
        confirmation_rows = _load_legacy_rows(source)
        if _fingerprint(confirmation_rows) != fingerprint:
            raise GithubDataMigrationError(
                "Historical GitHub data changed during migration; cutover was not recorded"
            )
        store.validate_legacy_rows(rows)
    except sqlite3.Error as exc:
        raise GithubDataMigrationError("GitHub DLC target migration failed") from exc
    return GithubDataMigrationResult(
        source_row_count=len(rows),
        source_fingerprint=fingerprint,
        target_changed=changed,
    )


def transitional_store(source: Session) -> TransitionalGithubBindingStore:
    """Return the cut-over target without consulting historical Core rows."""
    return TransitionalGithubBindingStore(github_dlc_data_path(source.get_bind()))
