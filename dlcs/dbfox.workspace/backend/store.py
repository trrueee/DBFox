from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from dbfox_dlc_api import ProjectResourceDescriptor, ResourceScopeRef

from .contracts import WorkspaceBinding
from .service import WorkspaceService


class WorkspaceBindingStore:
    def __init__(self, data_path: Path) -> None:
        data_path.mkdir(parents=True, exist_ok=True)
        self.database_path = data_path / "state.sqlite3"
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
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
                PRAGMA user_version = 1;
            """)

    @staticmethod
    def _binding(row: sqlite3.Row) -> WorkspaceBinding:
        return WorkspaceBinding.model_validate(dict(row))

    def get_project_binding(self, project_id: str) -> WorkspaceBinding | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workspace_bindings WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return self._binding(row) if row is not None else None

    def create_binding(self, project_id: str, root_path: str) -> WorkspaceBinding:
        service = WorkspaceService(root_path)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection, connection:
            existing = connection.execute(
                "SELECT id FROM workspace_bindings WHERE project_id = ?", (project_id,)
            ).fetchone()
            if existing is not None:
                raise ValueError("This Project already has a workspace binding")
            connection.execute(
                """INSERT INTO workspace_bindings
                   (id, project_id, root_path, root_digest, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (project_id, project_id, str(service.root), service.root_digest, now, now),
            )
        binding = self.get_project_binding(project_id)
        if binding is None:
            raise RuntimeError("Created workspace binding could not be reloaded")
        return binding

    def delete_binding(self, project_id: str) -> bool:
        with self._connect() as connection, connection:
            cursor = connection.execute(
                "DELETE FROM workspace_bindings WHERE project_id = ?", (project_id,)
            )
        return cursor.rowcount == 1

    def list_resources(self, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        binding = self.get_project_binding(project_id)
        if binding is None:
            return ()
        return (
            ProjectResourceDescriptor(
                kind="workspace",
                id=binding.id,
                version=binding.root_digest,
                name=Path(binding.root_path).name or "Workspace",
            ),
        )

    def resolve(self, ref: ResourceScopeRef) -> WorkspaceService:
        if ref.kind != "workspace":
            raise KeyError(ref.kind)
        binding = self.get_project_binding(str(ref.id))
        if binding is None:
            raise ValueError("Workspace binding does not exist")
        service = WorkspaceService(binding.root_path)
        if binding.root_digest != str(ref.version or "") or service.root_digest != binding.root_digest:
            raise ValueError("Workspace binding version no longer matches its canonical root")
        return service
