from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex

from dbfox_dlc_api import ProjectResourceDescriptor, ResourceScopeRef

from .contracts import WorkspaceBinding
from .service import WorkspaceService

WORKSPACE_RESOURCE_KIND = "dbfox.workspace.root"


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
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS workspace_bindings (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL UNIQUE,
                    root_path TEXT NOT NULL,
                    root_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_workspace_bindings_project ON workspace_bindings(project_id)"
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(workspace_bindings)")}
            if "binding_generation" not in columns:
                connection.execute(
                    "ALTER TABLE workspace_bindings ADD COLUMN binding_generation TEXT NOT NULL DEFAULT ''"
                )
            # Preserve references to existing bindings. Every new grant gets an
            # independent identity, including a rebind of the same directory.
            connection.execute(
                "UPDATE workspace_bindings SET binding_generation = root_digest WHERE binding_generation = ''"
            )
            connection.execute("PRAGMA user_version = 2")

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
        service = WorkspaceService(root_path, mutation_database=self.database_path)
        now = datetime.now(UTC).isoformat()
        binding = WorkspaceBinding(
            id=project_id,
            project_id=project_id,
            root_path=str(service.root),
            root_digest=service.root_digest,
            binding_generation=token_hex(32),
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id FROM workspace_bindings WHERE project_id = ?", (project_id,)
            ).fetchone()
            if existing is not None:
                raise ValueError("This Project already has a workspace binding")
            connection.execute(
                """INSERT INTO workspace_bindings
                   (id, project_id, root_path, root_digest, binding_generation, created_at, updated_at)
                   VALUES (:id, :project_id, :root_path, :root_digest, :binding_generation, :created_at, :updated_at)""",
                binding.model_dump(),
            )
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
                kind=WORKSPACE_RESOURCE_KIND,
                id=binding.id,
                version=binding.binding_generation,
                name=Path(binding.root_path).name or "Workspace",
            ),
        )

    def resolve(self, ref: ResourceScopeRef) -> WorkspaceService:
        if ref.kind != WORKSPACE_RESOURCE_KIND:
            raise KeyError(ref.kind)
        binding = self.get_project_binding(str(ref.id))
        if binding is None:
            raise ValueError("Workspace binding does not exist")
        if binding.binding_generation != str(ref.version or ""):
            raise ValueError("Workspace binding generation has been revoked")

        def check_binding(connection: sqlite3.Connection) -> None:
            row = connection.execute(
                "SELECT binding_generation FROM workspace_bindings WHERE project_id = ?", (binding.project_id,)
            ).fetchone()
            if row is None or row[0] != binding.binding_generation:
                raise ValueError("Workspace binding generation has been revoked")

        service = WorkspaceService(
            binding.root_path, mutation_database=self.database_path, check_binding=check_binding,
        )
        if service.root_digest != binding.root_digest:
            raise ValueError("Workspace binding version no longer matches its canonical root")
        return service
