"""SQLite backup and isolated restore owned by dbfox.data."""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .connection_primitives import existing_regular_file
from .contracts import BackupRecord, DatabaseHandle, RestoreResult
from .store import DataStateStore


class DataBackupService:
    """Use SQLite's official online-backup API; other providers fail closed."""

    def __init__(self, store: DataStateStore, data_path: Path) -> None:
        self._store = store
        self._backup_root = data_path / "backups"
        self._restore_root = data_path / "restores"
        self._backup_root.mkdir(parents=True, exist_ok=True)
        self._restore_root.mkdir(parents=True, exist_ok=True)

    def _handle(self, project_id: str, database_id: str) -> DatabaseHandle:
        database = self._store.get_database(database_id)
        if database is None:
            raise KeyError("Database resource is unavailable")
        profile = self._store.get_profile(database.connection_profile_id)
        if profile is None or profile.project_id != project_id:
            raise KeyError("Database resource is unavailable in this Project")
        if profile.provider != "sqlite":
            raise ValueError(
                "Backup is unavailable for this provider until its pinned official native client is bundled."
            )
        return DatabaseHandle(
            profile=profile,
            database=database,
            scope_version=(
                f"{profile.connection_generation}:{database.resource_generation}"
            ),
        )

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _online_copy(source_path: Path, destination_path: Path) -> int:
        source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True, timeout=5)
        destination = sqlite3.connect(destination_path, timeout=5)
        try:
            source.backup(destination, pages=128, sleep=0.05)
            integrity = destination.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or str(integrity[0]).casefold() != "ok":
                raise RuntimeError("SQLite backup integrity validation failed")
            table_count = int(
                destination.execute(
                    """
                    SELECT count(*) FROM sqlite_master
                     WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                ).fetchone()[0]
            )
            destination.commit()
        finally:
            destination.close()
            source.close()
        with destination_path.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        return table_count

    def create(
        self,
        *,
        project_id: str,
        database_id: str,
        label: str | None,
    ) -> BackupRecord:
        handle = self._handle(project_id, database_id)
        source_path = existing_regular_file(
            handle.database.database_name,
            label="SQLite",
        )
        file_name = f"backup_{uuid4().hex}.sqlite3"
        final_path = self._backup_root / file_name
        staging_path = self._backup_root / f".{file_name}.staging"
        stored = self._store.create_backup_record(
            project_id=project_id,
            database_resource_id=database_id,
            resource_version=handle.scope_version,
            source_database_name=str(source_path),
            label=label,
            file_name=file_name,
        )
        try:
            self._online_copy(source_path, staging_path)
            os.replace(staging_path, final_path)
            size = final_path.stat().st_size
            if size <= 0:
                raise RuntimeError("SQLite backup file is empty")
            return self._store.complete_backup_record(
                stored.record.id,
                file_size_bytes=size,
                checksum_sha256=self._checksum(final_path),
            ).record
        except Exception:
            self._store.fail_backup_record(stored.record.id)
            for path in (staging_path, final_path):
                if path.is_file() and path.parent == self._backup_root:
                    path.unlink()
            raise

    def list(
        self,
        *,
        project_id: str,
        database_id: str | None,
    ) -> tuple[BackupRecord, ...]:
        return self._store.list_backups(project_id, database_id)

    def restore(
        self,
        *,
        project_id: str,
        backup_id: str,
        expected_resource_version: str,
    ) -> RestoreResult:
        stored = self._store.get_backup(project_id, backup_id)
        if stored is None or stored.record.status != "success":
            raise KeyError("Successful backup is unavailable in this Project")
        handle = self._handle(project_id, stored.record.database_resource_id)
        if handle.scope_version != expected_resource_version:
            raise ValueError("Database resource version changed before restore")
        backup_path = self._backup_root / stored.file_name
        if not backup_path.is_file() or backup_path.parent != self._backup_root:
            raise RuntimeError("Backup payload is unavailable")
        if self._checksum(backup_path) != stored.record.checksum_sha256:
            raise RuntimeError("Backup payload checksum validation failed")

        target_path = self._restore_root / f"restore_{uuid4().hex}.sqlite3"
        try:
            table_count = self._online_copy(backup_path, target_path)
            committed = self._store.commit_sqlite_restore(
                project_id=project_id,
                backup_id=stored.record.id,
                database_resource_id=stored.record.database_resource_id,
                expected_resource_version=expected_resource_version,
                source_database_name=stored.record.source_database_name,
                target_database_name=str(target_path),
                validated_table_count=table_count,
            )
        except Exception:
            if target_path.is_file() and target_path.parent == self._restore_root:
                target_path.unlink()
            raise
        return RestoreResult(
            id=str(committed["id"]),
            backup_id=stored.record.id,
            database_resource_id=stored.record.database_resource_id,
            status="success",
            source_database_name=stored.record.source_database_name,
            target_database_name=str(target_path),
            previous_resource_version=expected_resource_version,
            committed_resource_version=str(committed["committed_resource_version"]),
            validated_table_count=table_count,
            completed_at=str(committed["completed_at"]),
        )
