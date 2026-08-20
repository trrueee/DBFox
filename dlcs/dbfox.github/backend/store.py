"""DLC-owned SQLite repository binding store."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dbfox_dlc_api import ProjectResourceDescriptor, ResourceScopeRef

from .contracts import GithubBinding


class GithubBindingStore:
    def __init__(self, data_path: Path) -> None:
        data_path.mkdir(parents=True, exist_ok=True)
        self.database_path = data_path / "state.sqlite3"
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
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
                PRAGMA user_version = 1;
                """
            )

    @staticmethod
    def _binding(row: sqlite3.Row) -> GithubBinding:
        return GithubBinding.model_validate(dict(row))

    def list_bindings(self, project_id: str) -> list[GithubBinding]:
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

    def get_binding(self, binding_id: str) -> GithubBinding | None:
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

    def get_project_binding(self, project_id: str, binding_id: str) -> GithubBinding | None:
        binding = self.get_binding(binding_id)
        return binding if binding is not None and binding.project_id == project_id else None

    def create_binding(
        self,
        *,
        project_id: str,
        owner: str,
        repository: str,
        ref_name: str,
        resolved_revision: str,
        default_branch: str | None,
        description: str | None,
    ) -> GithubBinding:
        now = datetime.now(UTC).isoformat()
        binding_id = str(uuid4())
        try:
            with self._connect() as connection, connection:
                connection.execute(
                    """
                    INSERT INTO repository_bindings (
                        id, project_id, owner, repository, ref_name,
                        resolved_revision, default_branch, description,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        binding_id,
                        project_id,
                        owner,
                        repository,
                        ref_name,
                        resolved_revision,
                        default_branch,
                        description,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Binding for {owner}/{repository}@{ref_name} already exists in this project."
            ) from exc
        binding = self.get_binding(binding_id)
        if binding is None:
            raise RuntimeError("Created GitHub binding could not be reloaded")
        return binding

    def update_binding(
        self,
        binding_id: str,
        *,
        ref_name: str,
        resolved_revision: str,
        default_branch: str | None,
        description: str | None,
    ) -> GithubBinding:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection, connection:
            cursor = connection.execute(
                """
                UPDATE repository_bindings
                   SET ref_name = ?, resolved_revision = ?, default_branch = ?,
                       description = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    ref_name,
                    resolved_revision,
                    default_branch,
                    description,
                    now,
                    binding_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"GitHub binding not found: {binding_id}")
        binding = self.get_binding(binding_id)
        if binding is None:
            raise RuntimeError("Updated GitHub binding could not be reloaded")
        return binding

    def delete_binding(self, project_id: str, binding_id: str) -> bool:
        with self._connect() as connection, connection:
            cursor = connection.execute(
                "DELETE FROM repository_bindings WHERE id = ? AND project_id = ?",
                (binding_id, project_id),
            )
        return cursor.rowcount == 1

    def list_resources(self, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        return tuple(
            ProjectResourceDescriptor(
                kind="github.repository",
                id=binding.id,
                version=binding.resolved_revision,
                name=f"{binding.owner}/{binding.repository}",
            )
            for binding in self.list_bindings(project_id)
        )

    def resolve(self, ref: ResourceScopeRef) -> GithubBinding:
        if ref.kind != "github.repository":
            raise KeyError(f"Unexpected resource kind: {ref.kind}")
        binding = self.get_binding(str(ref.id))
        if binding is None:
            raise ValueError(f"GitHub repository binding '{ref.id}' does not exist")
        if binding.resolved_revision != str(ref.version or ""):
            raise ValueError(
                f"GitHub repository binding '{ref.id}' revision does not match the authorized scope"
            )
        return binding
