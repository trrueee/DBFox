"""Historical one-way import of Core GitHub rows into DLC-owned SQLite.

This module belongs to the Alembic migration boundary.  It is deliberately not
part of the engine runtime graph: current GitHub behavior is owned by the
``dbfox.github`` DLC, while old Core rows remain available for upgrades from
pre-R5 databases.
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
    """Fail-closed historical import or target-store integrity error."""


@dataclass(frozen=True)
class GithubDataMigrationResult:
    source_row_count: int
    source_fingerprint: str
    target_changed: bool


def _metadata_database_path(bind: Engine | Connection) -> Path:
    engine = bind.engine if isinstance(bind, Connection) else bind
    if engine.dialect.name != "sqlite" or not engine.url.database:
        raise GithubDataMigrationError(
            "GitHub DLC migration requires a file-backed SQLite database"
        )
    return Path(engine.url.database).resolve()


def github_dlc_data_path(bind: Engine | Connection) -> Path:
    """Resolve product storage while keeping isolated migration tests isolated."""
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
    row: RowMapping | sqlite3.Row | dict[str, Any],
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


class GithubLegacyImportTarget:
    """Migration-only writer for the authoritative DLC database."""

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

    def sync(self, rows: Sequence[dict[str, str | None]]) -> bool:
        """Synchronize only identities owned by an uncompleted import."""
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

    def validate(self, rows: Sequence[dict[str, str | None]]) -> None:
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


def migrate_legacy_github_data(
    source: Session | Connection,
    *,
    data_path: Path | None = None,
) -> GithubDataMigrationResult:
    """Commit and verify target data before Alembic records the revision."""
    bind = source.get_bind() if isinstance(source, Session) else source
    target = GithubLegacyImportTarget(data_path or github_dlc_data_path(bind))
    rows = _load_legacy_rows(source)
    fingerprint = _fingerprint(rows)
    try:
        changed = target.sync(rows)
        confirmation_rows = _load_legacy_rows(source)
        if _fingerprint(confirmation_rows) != fingerprint:
            raise GithubDataMigrationError(
                "Historical GitHub data changed during migration; cutover was not recorded"
            )
        target.validate(rows)
    except sqlite3.Error as exc:
        raise GithubDataMigrationError("GitHub DLC target migration failed") from exc
    return GithubDataMigrationResult(
        source_row_count=len(rows),
        source_fingerprint=fingerprint,
        target_changed=changed,
    )
