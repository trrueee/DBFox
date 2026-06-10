"""LongTermMemory store â€?cross-session persistent memories.

Backed by an in-memory store (first phase) with the same API surface
that a PostgresStore / SQLiteStore would provide in production.

Memories are organized by *namespace* (tuple[str, ...]) and retrieved
with namespace-filtered queries.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from engine.memory.memory_schema import (
    MemoryRecord,
    MemoryType,
    MemoryStatus,
    MemorySource,
)

logger = logging.getLogger("databox.memory.long_term")


class LongTermMemoryStore:
    """In-memory long-term memory store with namespace isolation.

    Production should replace with a DB-backed implementation
    (PostgresStore, SQLiteStore, etc.) sharing the same interface.
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
        results: list[MemoryRecord] = []
        for rec in self._records.values():
            if rec.status == "deleted":
                continue
            if status and rec.status != status:
                continue
            # Handle expired records
            if rec.expires_at:
                try:
                    expiry = datetime.fromisoformat(rec.expires_at)
                    if datetime.now(timezone.utc) > expiry:
                        continue
                except (ValueError, TypeError):
                    pass

            # Namespace filter
            if namespaces:
                if not any(self._ns_matches(rec.namespace, ns) for ns in namespaces):
                    continue
            else:
                # Scoped filters
                if user_id and not any(part == user_id for part in rec.namespace):
                    continue
                if datasource_id and rec.datasource_id and rec.datasource_id != datasource_id:
                    continue
                if project_id and rec.project_id and rec.project_id != project_id:
                    continue

            # Type filter
            if types and rec.type not in types:
                continue

            # Confidence filter
            if rec.confidence < min_confidence:
                continue

            # Keyword filter (simple substring match on text)
            if keywords:
                text_lower = rec.text.lower()
                if not any(kw.lower() in text_lower for kw in keywords):
                    continue

            results.append(rec)

        # Sort by confidence desc, then recency
        results.sort(key=lambda r: (r.confidence, r.updated_at), reverse=True)
        return results[:limit]

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


# Module-level singleton
_store: LongTermMemoryStore | None = None


def get_long_term_store() -> LongTermMemoryStore:
    global _store
    if _store is None:
        _store = LongTermMemoryStore()
    return _store
