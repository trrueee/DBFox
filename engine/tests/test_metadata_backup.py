from __future__ import annotations

import sqlite3
import time
import os

from engine.persistence.backup import MetadataBackupService


def test_backup_sqlite_captures_committed_wal_rows(tmp_path) -> None:
    db_path = tmp_path / "metadata.sqlite"
    backup_path = tmp_path / "metadata.sqlite.bak"

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=100000")
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("INSERT INTO items (name) VALUES ('from-wal')")
    conn.commit()

    try:
        MetadataBackupService.backup_sqlite(db_path, backup_path)
    finally:
        conn.close()

    backup_conn = sqlite3.connect(backup_path)
    try:
        rows = backup_conn.execute("SELECT name FROM items").fetchall()
    finally:
        backup_conn.close()

    assert rows == [("from-wal",)]


def test_prune_old_backups_keeps_newest_files(tmp_path) -> None:
    db_path = tmp_path / "metadata.sqlite"
    backups = []
    for index in range(4):
        path = tmp_path / f"metadata.sqlite.bak_{index}"
        path.write_text(str(index), encoding="utf-8")
        ts = time.time() + index
        os.utime(path, (ts, ts))
        backups.append(path)

    MetadataBackupService.prune_old_backups(db_path, limit=2)

    assert backups[0].exists() is False
    assert backups[1].exists() is False
    assert backups[2].exists() is True
    assert backups[3].exists() is True
