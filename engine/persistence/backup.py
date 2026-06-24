from __future__ import annotations

import sqlite3
from pathlib import Path


class MetadataBackupService:
    @staticmethod
    def backup_sqlite(db_path: Path, backup_path: Path) -> None:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path)) as src:
            with sqlite3.connect(str(backup_path)) as dst:
                src.backup(dst)

    @staticmethod
    def restore_sqlite(backup_path: Path, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(backup_path)) as src:
            with sqlite3.connect(str(db_path)) as dst:
                src.backup(dst)

    @staticmethod
    def prune_old_backups(db_path: Path, limit: int = 5) -> None:
        if limit < 1:
            return
        backups = sorted(
            db_path.parent.glob(f"{db_path.name}.bak_*"),
            key=lambda path: (path.stat().st_mtime, path.name),
        )
        for old_backup in backups[:-limit]:
            try:
                old_backup.unlink()
            except OSError:
                pass
