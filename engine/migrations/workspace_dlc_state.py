"""One-way import of Project workspace roots into dbfox.workspace state."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, bindparam, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session


class WorkspaceDataMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspaceDataMigrationResult:
    source_row_count: int
    target_changed: bool


def _metadata_database_path(bind: Engine | Connection) -> Path:
    engine = bind.engine if isinstance(bind, Connection) else bind
    if engine.dialect.name != "sqlite" or not engine.url.database:
        raise WorkspaceDataMigrationError(
            "Workspace DLC migration requires a file-backed SQLite database"
        )
    return Path(engine.url.database).resolve()


def workspace_dlc_data_path(bind: Engine | Connection) -> Path:
    metadata_path = _metadata_database_path(bind)
    from engine.db import DB_PATH
    from engine.runtime_paths import private_runtime_dir

    if metadata_path == DB_PATH.resolve():
        storage_root = private_runtime_dir("dlcs")
    else:
        storage_root = metadata_path.parent / "dlcs"
        storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root / "data" / "dbfox.workspace"


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return datetime.fromisoformat(value).isoformat()
    raise WorkspaceDataMigrationError("Historical Workspace timestamp is invalid")


def _canonical_row(row: RowMapping | sqlite3.Row | dict[str, Any]) -> dict[str, str]:
    values = dict(row)
    root = str(values["workspace_root"]).strip()
    canonical_root = str(Path(root).expanduser().resolve(strict=False))
    return {
        "id": str(values["id"]),
        "project_id": str(values["id"]),
        "root_path": canonical_root,
        "root_digest": hashlib.sha256(canonical_root.encode("utf-8")).hexdigest()[:16],
        "created_at": _timestamp(values["created_at"]),
        "updated_at": _timestamp(values["updated_at"]),
    }


def _legacy_rows(source: Session | Connection) -> list[dict[str, str]]:
    rows = source.execute(text("""
        SELECT id, workspace_root, created_at, updated_at
          FROM projects
         WHERE workspace_root IS NOT NULL AND trim(workspace_root) <> ''
         ORDER BY id
    """)).mappings()
    return [_canonical_row(row) for row in rows]


class WorkspaceLegacyImportTarget:
    def __init__(self, data_path: Path) -> None:
        data_path.mkdir(parents=True, exist_ok=True)
        self.database_path = data_path / "state.sqlite3"
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS workspace_bindings (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL UNIQUE,
                    root_path TEXT NOT NULL,
                    root_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_workspace_bindings_project
                    ON workspace_bindings(project_id);
                CREATE TABLE IF NOT EXISTS legacy_core_import_rows (
                    project_id TEXT PRIMARY KEY
                );
                PRAGMA user_version = 1;
            """)

    def sync(self, rows: Sequence[dict[str, str]]) -> bool:
        changed = False
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                staged = {
                    str(row["project_id"])
                    for row in connection.execute(
                        "SELECT project_id FROM legacy_core_import_rows"
                    ).fetchall()
                }
                for row in rows:
                    existing = connection.execute(
                        "SELECT * FROM workspace_bindings WHERE project_id = ?",
                        (row["project_id"],),
                    ).fetchone()
                    if existing is not None and row["project_id"] not in staged:
                        comparable = {key: str(existing[key]) for key in row}
                        if comparable != row:
                            raise WorkspaceDataMigrationError(
                                "Workspace DLC target contains a conflicting binding"
                            )
                    if existing is None:
                        connection.execute(
                            """INSERT INTO workspace_bindings
                               (id, project_id, root_path, root_digest, created_at, updated_at)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            tuple(row[key] for key in (
                                "id", "project_id", "root_path", "root_digest",
                                "created_at", "updated_at",
                            )),
                        )
                        changed = True
                    connection.execute(
                        "INSERT OR IGNORE INTO legacy_core_import_rows(project_id) VALUES (?)",
                        (row["project_id"],),
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return changed

    def validate(self, rows: Sequence[dict[str, str]]) -> None:
        with self._connect() as connection:
            for row in rows:
                target = connection.execute(
                    "SELECT * FROM workspace_bindings WHERE project_id = ?",
                    (row["project_id"],),
                ).fetchone()
                if target is None or any(str(target[key]) != value for key, value in row.items()):
                    raise WorkspaceDataMigrationError(
                        "Workspace DLC target validation failed before cutover"
                    )


def migrate_legacy_workspace_data(
    source: Session | Connection,
    *,
    data_path: Path | None = None,
) -> WorkspaceDataMigrationResult:
    bind = source.get_bind() if isinstance(source, Session) else source
    target = WorkspaceLegacyImportTarget(data_path or workspace_dlc_data_path(bind))
    rows = _legacy_rows(source)
    try:
        changed = target.sync(rows)
        target.validate(rows)
    except sqlite3.Error as exc:
        raise WorkspaceDataMigrationError("Workspace DLC target migration failed") from exc
    if rows:
        source.execute(
            text("UPDATE projects SET workspace_root = NULL WHERE id IN :ids")
            .bindparams(bindparam("ids", expanding=True)),
            {"ids": [row["project_id"] for row in rows]},
        )
    return WorkspaceDataMigrationResult(
        source_row_count=len(rows),
        target_changed=changed,
    )
