"""LongTermMemory store — cross-session persistent memories.

Backed by SQLite by default, with an in-memory implementation available
for tests and local debugging.

Memories are organized by *namespace* (tuple[str, ...]) and retrieved
with namespace-filtered queries.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
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

logger = logging.getLogger("databox.memory.long_term")


class LongTermMemoryStore:
    """In-memory long-term memory store with namespace isolation.

    Intended for tests and local debugging. Production uses
    SQLiteLongTermMemoryStore through get_long_term_store().
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
        logger.debug("Memory put: ns=%s key=%s type=%s", record.namespace, record.key, record.type)
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
        # Override the auto-generated id/key with our explicit key
        record.id = key
        return self.put(record)

    def delete(self, memory_id: str) -> bool:
        if memory_id in self._records:
            self._records[memory_id].status = "deleted"
            return True
        return False

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, memory_id: str) -> MemoryRecord | None:
        rec = self._records.get(memory_id)
        if rec and rec.status != "deleted":
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

    def list_by_namespace(self, namespace: tuple[str, ...]) -> list[MemoryRecord]:
        return [r for r in self._records.values()
                if r.status != "deleted" and self._ns_matches(r.namespace, namespace)]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ns_matches(rec_ns: tuple[str, ...], query_ns: tuple[str, ...]) -> bool:
        """Check if *rec_ns* starts with *query_ns* prefix."""
        if len(query_ns) > len(rec_ns):
            return False
        return rec_ns[:len(query_ns)] == query_ns

    def _find_by_namespace_key(self, namespace: tuple[str, ...], key: str) -> MemoryRecord | None:
        for rec in self._records.values():
            if rec.namespace == namespace and rec.key == key and rec.status != "deleted":
                return rec
        return None

    def all(self) -> list[MemoryRecord]:
        return [r for r in self._records.values() if r.status != "deleted"]

    def count(self) -> int:
        return len(self.all())


class SQLiteLongTermMemoryStore:
    """SQLite-backed implementation of the long-term memory store API."""

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
        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
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
                    json.dumps(list(record.namespace), ensure_ascii=False),
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
        logger.debug("SQLite memory put: ns=%s key=%s type=%s", record.namespace, record.key, record.type)
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
        if record is None or record.status == "deleted":
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
        return _search_records(
            self._load_records(),
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

    def list_by_namespace(self, namespace: tuple[str, ...]) -> list[MemoryRecord]:
        return [
            record for record in self._load_records()
            if record.status != "deleted" and LongTermMemoryStore._ns_matches(record.namespace, namespace)
        ]

    def all(self) -> list[MemoryRecord]:
        return [record for record in self._load_records() if record.status != "deleted"]

    def count(self) -> int:
        return len(self.all())

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

    def _load_records(self) -> list[MemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM long_term_memories").fetchall()
        records: list[MemoryRecord] = []
        for row in rows:
            record = self._record_from_payload(str(row["payload"]))
            if record is not None:
                records.append(record)
        return records

    def _find_by_namespace_key(self, namespace: tuple[str, ...], key: str) -> MemoryRecord | None:
        for rec in self._load_records():
            if rec.namespace == namespace and rec.key == key and rec.status != "deleted":
                return rec
        return None

    def _record_from_payload(self, payload: str) -> MemoryRecord | None:
        try:
            return MemoryRecord.model_validate(json.loads(payload))
        except Exception as exc:
            logger.warning("Skipping corrupt long-term memory record: %s", exc)
            return None


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
    results: list[MemoryRecord] = []
    for rec in records:
        if rec.status == "deleted":
            continue
        if status and rec.status != status:
            continue
        if _is_expired(rec):
            continue

        if namespaces:
            if not any(LongTermMemoryStore._ns_matches(rec.namespace, ns) for ns in namespaces):
                continue
        else:
            if user_id and not any(part == user_id for part in rec.namespace):
                continue
            if datasource_id and rec.datasource_id and rec.datasource_id != datasource_id:
                continue
            if project_id and rec.project_id and rec.project_id != project_id:
                continue

        if types and rec.type not in types:
            continue
        if rec.confidence < min_confidence:
            continue
        if keywords:
            text_lower = rec.text.lower()
            if not any(kw.lower() in text_lower for kw in keywords):
                continue
        results.append(rec)

    results.sort(key=lambda r: (r.confidence, r.updated_at), reverse=True)
    return results[:limit]


def _is_expired(record: MemoryRecord) -> bool:
    if not record.expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(record.expires_at)
    except (ValueError, TypeError):
        return False
    return datetime.now(timezone.utc) > expiry


# Module-level singleton
_store: LongTermMemoryStore | SQLiteLongTermMemoryStore | None = None


def get_long_term_store() -> LongTermMemoryStore | SQLiteLongTermMemoryStore:
    global _store
    if _store is None:
        if os.environ.get("DATABOX_MEMORY_STORE", "").lower() == "memory":
            _store = LongTermMemoryStore()
        else:
            _store = SQLiteLongTermMemoryStore(
                private_runtime_file("memory", "long_term_memory.sqlite")
            )
    return _store
