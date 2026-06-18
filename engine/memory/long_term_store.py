"""LongTermMemory store — cross-session persistent memories.

Backed by SQLite by default, with an in-memory implementation available
for tests and local debugging.

Memories are organized by *namespace* (tuple[str, ...]) and retrieved
with namespace-filtered queries.

Namespace storage format
------------------------
Inside the SQLite ``namespace`` column, namespaces are stored as
slash-delimited text (e.g. ``user/u1/project/p1``) so that SQL ``LIKE``
prefix queries can push filtering to the database layer.  Older rows
that still hold a JSON-array literal (``["user","u1",...]``) are
transparently normalised when read.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from engine.runtime_paths import private_runtime_file
from engine.memory.memory_schema import (
    MemoryRecord,
    MemoryType,
    MemoryStatus,
    MemorySource,
)

logger = logging.getLogger("dbfox.memory.long_term")

# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------


def _namespace_to_text(ns: tuple[str, ...]) -> str:
    """Serialize a namespace tuple to a slash-delimited path."""
    return "/".join(ns)


def _namespace_from_text(text: str) -> tuple[str, ...]:
    """Parse a namespace that was stored as slash-delimited text.

    Also handles legacy JSON-array rows (e.g. ``["user","u1"]``) so that
    existing databases can be read without a migration.
    """
    if not text:
        return ()
    stripped = text.strip()
    if stripped.startswith("["):
        # Legacy JSON-array format
        try:
            parts = json.loads(stripped)
            if isinstance(parts, list):
                return tuple(str(p) for p in parts)
        except (json.JSONDecodeError, TypeError):
            pass
    return tuple(stripped.split("/"))


def _namespace_like_prefix(ns: tuple[str, ...]) -> str:
    """Return a LIKE pattern that matches records whose namespace starts
    with *ns* (prefix match)."""
    return _namespace_to_text(ns) + "/%"


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------


class LongTermMemoryStore:
    """In-memory long-term memory store with namespace isolation.

    Intended for tests and local debugging.  Production uses
    ``SQLiteLongTermMemoryStore`` through ``get_long_term_store()``.
    """

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def put(self, record: MemoryRecord) -> MemoryRecord:
        """Insert or update a memory record."""
        existing = self._find_by_namespace_key(record.namespace, record.key)
        if existing:
            record.id = existing.id
            record.created_at = existing.created_at
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._records[record.id] = record
        logger.debug(
            "Memory put: ns=%s key=%s type=%s",
            record.namespace,
            record.key,
            record.type,
        )
        return record

    def upsert(
        self,
        *,
        namespace: tuple[str, ...],
        key: str,
        type: MemoryType,
        text: str,
        content: dict[str, Any] | None = None,
        source: MemorySource = "system_generated",
        confidence: float = 1.0,
        status: MemoryStatus = "active",
        **kwargs: Any,
    ) -> MemoryRecord:
        """Convenience: upsert a memory by namespace + key."""
        record = MemoryRecord(
            namespace=namespace,
            type=type,
            text=text,
            content=content or {},
            source=source,
            confidence=confidence,
            status=status,
            **kwargs,
        )
        record.id = key
        return self.put(record)

    def delete(self, memory_id: str) -> bool:
        if memory_id in self._records:
            self._records[memory_id].status = "deleted"
            return True
        return False

    def purge(self) -> int:
        """Remove soft-deleted and expired records from the store."""
        to_remove = [
            mid
            for mid, rec in self._records.items()
            if rec.status == "deleted" or _is_expired(rec)
        ]
        for mid in to_remove:
            del self._records[mid]
        if to_remove:
            logger.debug("Purged %d stale long-term memory records", len(to_remove))
        return len(to_remove)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, memory_id: str) -> MemoryRecord | None:
        rec = self._records.get(memory_id)
        if rec and rec.status != "deleted" and not _is_expired(rec):
            return rec
        return None

    def search(
        self,
        *,
        namespaces: list[tuple[str, ...]] | None = None,
        types: list[MemoryType] | None = None,
        status: MemoryStatus | None = None,
        keywords: list[str] | None = None,
        user_id: str | None = None,
        datasource_id: str | None = None,
        project_id: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        """Search memories with namespace + type + keyword filters."""
        return _search_records(
            self._records.values(),
            namespaces=namespaces,
            types=types,
            status=status,
            keywords=keywords,
            user_id=user_id,
            datasource_id=datasource_id,
            project_id=project_id,
            min_confidence=min_confidence,
            limit=limit,
        )

    def list_by_namespace(
        self, namespace: tuple[str, ...]
    ) -> list[MemoryRecord]:
        return [
            r
            for r in self._records.values()
            if r.status != "deleted"
            and not _is_expired(r)
            and self._ns_matches(r.namespace, namespace)
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ns_matches(
        rec_ns: tuple[str, ...], query_ns: tuple[str, ...]
    ) -> bool:
        """Check if *rec_ns* starts with *query_ns* prefix."""
        if len(query_ns) > len(rec_ns):
            return False
        return rec_ns[: len(query_ns)] == query_ns

    def _find_by_namespace_key(
        self, namespace: tuple[str, ...], key: str
    ) -> MemoryRecord | None:
        for rec in self._records.values():
            if (
                rec.namespace == namespace
                and rec.key == key
                and rec.status != "deleted"
            ):
                return rec
        return None

    def all(self) -> list[MemoryRecord]:
        return [
            r
            for r in self._records.values()
            if r.status != "deleted" and not _is_expired(r)
        ]

    def count(self) -> int:
        return len(self.all())


# ---------------------------------------------------------------------------
# SQLite-backed store
# ---------------------------------------------------------------------------


class SQLiteLongTermMemoryStore:
    """SQLite-backed implementation of the long-term memory store API.

    Pushes namespace / status / type / scope filters down to SQL WHERE
    clauses so that the store stays fast as the number of memories grows.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def put(self, record: MemoryRecord) -> MemoryRecord:
        existing = self._find_by_namespace_key(record.namespace, record.key)
        if existing:
            record.id = existing.id
            record.created_at = existing.created_at
        record.updated_at = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(
            record.model_dump(mode="json"), ensure_ascii=False
        )
        namespace_text = _namespace_to_text(record.namespace)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO long_term_memories (
                    id, namespace, type, status, confidence, text,
                    user_id, project_id, datasource_id, updated_at, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    namespace = excluded.namespace,
                    type = excluded.type,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    text = excluded.text,
                    user_id = excluded.user_id,
                    project_id = excluded.project_id,
                    datasource_id = excluded.datasource_id,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    record.id,
                    namespace_text,
                    record.type,
                    record.status,
                    record.confidence,
                    record.text,
                    record.user_id,
                    record.project_id,
                    record.datasource_id,
                    record.updated_at,
                    payload,
                ),
            )
        logger.debug(
            "SQLite memory put: ns=%s key=%s type=%s",
            record.namespace,
            record.key,
            record.type,
        )
        return record

    def upsert(
        self,
        *,
        namespace: tuple[str, ...],
        key: str,
        type: MemoryType,
        text: str,
        content: dict[str, Any] | None = None,
        source: MemorySource = "system_generated",
        confidence: float = 1.0,
        status: MemoryStatus = "active",
        **kwargs: Any,
    ) -> MemoryRecord:
        record = MemoryRecord(
            namespace=namespace,
            type=type,
            text=text,
            content=content or {},
            source=source,
            confidence=confidence,
            status=status,
            **kwargs,
        )
        record.id = key
        return self.put(record)

    def delete(self, memory_id: str) -> bool:
        rec = self.get(memory_id)
        if rec is None:
            return False
        rec.status = "deleted"
        self.put(rec)
        return True

    def purge(self) -> int:
        """Permanently remove soft-deleted and expired records.

        Collects all stale record IDs in a single scan, then executes one
        transaction to delete them — avoiding the N+1 per-record connection
        overhead of the previous implementation.
        """
        stale_ids: list[str] = []
        for rec in self._load_records(raw_only=True):
            if rec.status == "deleted" or _is_expired(rec):
                stale_ids.append(rec.id)

        if not stale_ids:
            return 0

        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                # Split into batches of 500 to avoid hitting SQLite's
                # SQLITE_MAX_VARIABLE_NUMBER (default 999).
                batch_size = 500
                for i in range(0, len(stale_ids), batch_size):
                    batch = stale_ids[i : i + batch_size]
                    placeholders = ",".join(["?"] * len(batch))
                    conn.execute(
                        f"DELETE FROM long_term_memories WHERE id IN ({placeholders})",
                        batch,
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        logger.debug("Purged %d stale long-term memory records", len(stale_ids))
        return len(stale_ids)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM long_term_memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        if row is None:
            return None
        record = self._record_from_payload(str(row["payload"]))
        if record is None or record.status == "deleted" or _is_expired(record):
            return None
        return record

    def search(
        self,
        *,
        namespaces: list[tuple[str, ...]] | None = None,
        types: list[MemoryType] | None = None,
        status: MemoryStatus | None = None,
        keywords: list[str] | None = None,
        user_id: str | None = None,
        datasource_id: str | None = None,
        project_id: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        """Search memories, pushing most filters to SQL."""
        where: list[str] = ["status != 'deleted'"]
        params: list[Any] = []

        if status:
            where.append("status = ?")
            params.append(status)

        if types:
            where.append(f"type IN ({','.join(['?'] * len(types))})")
            params.extend(types)

        if user_id:
            where.append("user_id = ?")
            params.append(user_id)

        if project_id:
            where.append("project_id = ?")
            params.append(project_id)

        if datasource_id:
            where.append("datasource_id = ?")
            params.append(datasource_id)

        if namespaces:
            ns_clauses: list[str] = []
            for ns in namespaces:
                prefix = _namespace_to_text(ns)
                ns_clauses.append("namespace = ?")
                params.append(prefix)
                ns_clauses.append("namespace LIKE ?")
                params.append(_namespace_like_prefix(ns))
            where.append(f"({' OR '.join(ns_clauses)})")

        if min_confidence > 0.0:
            where.append("confidence >= ?")
            params.append(min_confidence)

        sql = (
            "SELECT payload FROM long_term_memories"
            f" WHERE {' AND '.join(where)}"
            " ORDER BY confidence DESC, updated_at DESC"
            " LIMIT ?"
        )
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        records: list[MemoryRecord] = []
        for row in rows:
            record = self._record_from_payload(str(row["payload"]))
            if record is None:
                continue
            if _is_expired(record):
                continue
            records.append(record)

        # Keyword search still happens in Python (FTS would be overkill here)
        if keywords:
            records = [r for r in records if _matches_keywords(r, keywords)]

        return records[:limit]

    def list_by_namespace(
        self, namespace: tuple[str, ...]
    ) -> list[MemoryRecord]:
        prefix = _namespace_to_text(namespace)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM long_term_memories"
                " WHERE status != 'deleted'"
                " AND (namespace = ? OR namespace LIKE ?)"
                " ORDER BY namespace",
                (prefix, _namespace_like_prefix(namespace)),
            ).fetchall()
        records: list[MemoryRecord] = []
        for row in rows:
            record = self._record_from_payload(str(row["payload"]))
            if record is None or _is_expired(record):
                continue
            records.append(record)
        return records

    def all(self) -> list[MemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM long_term_memories WHERE status != 'deleted'"
            ).fetchall()
        records: list[MemoryRecord] = []
        for row in rows:
            record = self._record_from_payload(str(row["payload"]))
            if record is None or _is_expired(record):
                continue
            records.append(record)
        return records

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM long_term_memories WHERE status != 'deleted'"
            ).fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS long_term_memories (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    text TEXT NOT NULL,
                    user_id TEXT,
                    project_id TEXT,
                    datasource_id TEXT,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_long_term_memories_scope "
                "ON long_term_memories(user_id, project_id, datasource_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_long_term_memories_status "
                "ON long_term_memories(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_long_term_memories_namespace "
                "ON long_term_memories(namespace)"
            )

    def _load_records(
        self, *, raw_only: bool = False
    ) -> list[MemoryRecord]:
        """Load all records from the store.

        Args:
            raw_only: If True, return ALL records including deleted/expired
                      (used by ``purge()`` to find expired records).
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM long_term_memories"
            ).fetchall()
        records: list[MemoryRecord] = []
        for row in rows:
            record = self._record_from_payload(str(row["payload"]))
            if record is None:
                continue
            if not raw_only:
                if record.status == "deleted" or _is_expired(record):
                    continue
            records.append(record)
        return records

    def _find_by_namespace_key(
        self, namespace: tuple[str, ...], key: str
    ) -> MemoryRecord | None:
        namespace_text = _namespace_to_text(namespace)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM long_term_memories"
                " WHERE namespace = ? AND id = ? AND status != 'deleted'",
                (namespace_text, key),
            ).fetchone()
        if row is None:
            return None
        return self._record_from_payload(str(row["payload"]))

    def _record_from_payload(self, payload: str) -> MemoryRecord | None:
        try:
            return MemoryRecord.model_validate(json.loads(payload))
        except Exception as exc:
            logger.warning(
                "Skipping corrupt long-term memory record: %s", exc
            )
            return None


# ---------------------------------------------------------------------------
# Shared search logic (used by in-memory store only; SQLite store pushes
# filters to the DB layer and only uses this for keyword matching).
# ---------------------------------------------------------------------------


def _search_records(
    records: Iterable[MemoryRecord],
    *,
    namespaces: list[tuple[str, ...]] | None = None,
    types: list[MemoryType] | None = None,
    status: MemoryStatus | None = None,
    keywords: list[str] | None = None,
    user_id: str | None = None,
    datasource_id: str | None = None,
    project_id: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 20,
) -> list[MemoryRecord]:
    """Pure-Python filtering used by the in-memory store."""
    results: list[MemoryRecord] = []
    for rec in records:
        if rec.status == "deleted":
            continue
        if status and rec.status != status:
            continue
        if _is_expired(rec):
            continue

        if namespaces:
            if not any(
                LongTermMemoryStore._ns_matches(rec.namespace, ns)
                for ns in namespaces
            ):
                continue
        else:
            if user_id and not any(
                part == user_id for part in rec.namespace
            ):
                continue
            if (
                datasource_id
                and rec.datasource_id
                and rec.datasource_id != datasource_id
            ):
                continue
            if (
                project_id
                and rec.project_id
                and rec.project_id != project_id
            ):
                continue

        if types and rec.type not in types:
            continue
        if rec.confidence < min_confidence:
            continue
        if keywords:
            if not _matches_keywords(rec, keywords):
                continue
        results.append(rec)

    results.sort(key=lambda r: (r.confidence, r.updated_at), reverse=True)
    return results[:limit]


def _matches_keywords(record: MemoryRecord, keywords: list[str]) -> bool:
    """Check if *record.text* contains any of the *keywords* (case-insensitive)."""
    text_lower = record.text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _is_expired(record: MemoryRecord) -> bool:
    """Return True if *record* has a non-null ``expires_at`` that is in the past.

    Both offset-aware and offset-naive ISO-8601 strings are accepted.
    Naive timestamps are interpreted as UTC.
    """
    if not record.expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(record.expires_at)
    except (ValueError, TypeError):
        return False
    # Make offset-naive datetimes aware so they can be compared against
    # timezone-aware ``datetime.now(timezone.utc)`` (required in Python 3.12+).
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    try:
        return datetime.now(timezone.utc) > expiry
    except TypeError:
        # Defensive: if we still cannot compare, treat as not-expired
        return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store: LongTermMemoryStore | SQLiteLongTermMemoryStore | None = None
_store_lock = threading.Lock()


def get_long_term_store() -> LongTermMemoryStore | SQLiteLongTermMemoryStore:
    """Return the module-level singleton memory store, creating it on first call.

    Uses double-checked locking so that concurrent callers never create two
    instances of the backing SQLite store.
    """
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                if os.environ.get("DBFOX_MEMORY_STORE", "").lower() == "memory":
                    _store = LongTermMemoryStore()
                else:
                    _store = SQLiteLongTermMemoryStore(
                        private_runtime_file("memory", "long_term_memory.sqlite")
                    )
    return _store
