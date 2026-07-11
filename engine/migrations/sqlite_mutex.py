"""Cross-process locking for DBFox file-backed SQLite migrations."""
from __future__ import annotations

from contextlib import contextmanager
import math
import os
from pathlib import Path
import time
from typing import Iterator
from urllib.parse import unquote, urlencode, urlparse

import sqlalchemy as sa


SQLITE_MIGRATION_LOCKED = "DBFOX_ALEMBIC_SQLITE_MIGRATION_LOCKED"
_LOCK_TIMEOUT_ENV = "DBFOX_ALEMBIC_SQLITE_MUTEX_TIMEOUT_SECONDS"
_DEFAULT_LOCK_TIMEOUT_SECONDS = 30.0


def sqlite_file_target(database_url: str) -> tuple[str, bool] | None:
    """Return a sqlite3-compatible target only for persistent SQLite URLs."""
    url = sa.engine.make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        return None

    database = url.database
    if database == ":memory:" or database.startswith("file::memory:"):
        return None

    if database.startswith("file:"):
        query = [(key, value) for key, value in url.query.items() if key != "uri"]
        if any(key == "mode" and value == "memory" for key, value in query):
            return None
        suffix = urlencode(query, doseq=True)
        return (f"{database}?{suffix}" if suffix else database, True)

    return str(Path(database).resolve()), False


def sqlite_migration_lock_path(database_url: str) -> Path | None:
    """Locate the advisory mutex file beside a persistent SQLite database."""
    target = sqlite_file_target(database_url)
    if target is None:
        return None

    database, is_uri = target
    if not is_uri:
        database_path = Path(database)
    else:
        parsed = urlparse(database)
        database_path = Path(unquote(parsed.path))
        if os.name == "nt" and len(database_path.drive) == 0:
            raw_path = str(database_path)
            if len(raw_path) >= 3 and raw_path[0] in ("/", "\\") and raw_path[2] == ":":
                database_path = Path(raw_path[1:])

    return database_path.with_name(f"{database_path.name}.dbfox-migration.lock")


def _lock_timeout_seconds() -> float:
    raw_timeout = os.getenv(_LOCK_TIMEOUT_ENV)
    if raw_timeout is None:
        return _DEFAULT_LOCK_TIMEOUT_SECONDS
    try:
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise RuntimeError(
            "DBFOX_ALEMBIC_SQLITE_MIGRATION_LOCK_TIMEOUT_INVALID"
        ) from exc
    if not math.isfinite(timeout) or timeout < 0:
        raise RuntimeError("DBFOX_ALEMBIC_SQLITE_MIGRATION_LOCK_TIMEOUT_INVALID")
    return timeout


def _try_lock(lock_file) -> bool:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
    except BlockingIOError:
        return False
    return True


def _unlock(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


@contextmanager
def sqlite_migration_mutex(
    database_url: str,
    *,
    timeout_seconds: float | None = None,
) -> Iterator[None]:
    """Serialize cooperating DBFox migrations for one SQLite metadata file.

    The lock file is intentionally retained: deleting it after release races
    another process that already opened the old inode.  OS-level locks release
    automatically if a process exits unexpectedly.
    """
    lock_path = sqlite_migration_lock_path(database_url)
    if lock_path is None:
        yield
        return

    timeout = _lock_timeout_seconds() if timeout_seconds is None else timeout_seconds
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("timeout_seconds must be a finite non-negative value")

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()

        deadline = time.monotonic() + timeout
        while not _try_lock(lock_file):
            if time.monotonic() >= deadline:
                raise RuntimeError(f"{SQLITE_MIGRATION_LOCKED}: {lock_path}")
            time.sleep(0.05)
        try:
            yield
        finally:
            _unlock(lock_file)
