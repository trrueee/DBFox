"""Global connection pool registry with LRU eviction.

Tracks MySQL and PostgreSQL pools, enforces configurable limits, and evicts
least-recently-used idle pools when limits are exceeded.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.pool import QueuePool

logger = logging.getLogger("dbfox.sql.pool_registry")

MAX_POOLS = int(os.environ.get("DBFOX_SQL_MAX_POOLS", "16"))
MAX_CONNECTIONS = int(os.environ.get("DBFOX_SQL_MAX_CONNECTIONS", "64"))


@dataclass
class PoolEntry:
    pool: QueuePool
    key: tuple[Any, ...]
    last_used: float = field(default_factory=time.monotonic)
    capacity: int = 0  # pool_size + max_overflow


class PoolRegistry:
    """LRU-evicting registry for database connection pools."""

    def __init__(self, max_pools: int = MAX_POOLS, max_connections: int = MAX_CONNECTIONS) -> None:
        self._max_pools = max_pools
        self._max_connections = max_connections
        self._pools: dict[tuple[Any, ...], PoolEntry] = {}

    def get_or_create(
        self,
        key: tuple[Any, ...],
        creator: Any,
        pool_size: int = 5,
        max_overflow: int = 10,
        recycle: int = 1800,
    ) -> QueuePool:
        if key in self._pools:
            entry = self._pools[key]
            entry.last_used = time.monotonic()
            return entry.pool

        self._evict_if_needed(pool_size + max_overflow)

        pool = QueuePool(creator, pool_size=pool_size, max_overflow=max_overflow, recycle=recycle)
        self._pools[key] = PoolEntry(pool=pool, key=key, capacity=pool_size + max_overflow)
        logger.info(
            "PoolRegistry: created pool key=%s total_pools=%d total_capacity=%d",
            key, len(self._pools), self._total_capacity(),
        )
        return pool

    def has(self, key: tuple[Any, ...]) -> bool:
        """Check if a pool exists for the given key without allocating a creator closure."""
        return key in self._pools

    def _total_capacity(self) -> int:
        return sum(e.capacity for e in self._pools.values())

    def _evict_if_needed(self, new_pool_capacity: int) -> None:
        while len(self._pools) >= self._max_pools or (
            self._total_capacity() + new_pool_capacity > self._max_connections and self._pools
        ):
            if not self._pools:
                break
            lru_key = min(self._pools, key=lambda k: self._pools[k].last_used)
            entry = self._pools.pop(lru_key)
            try:
                entry.pool.dispose()
            except Exception:
                pass
            logger.info(
                "PoolRegistry: evicted pool key=%s capacity=%d",
                lru_key, entry.capacity,
            )

    def dispose_datasource(self, datasource_id: str) -> int:
        """Dispose all pools whose key starts with the given datasource_id.

        Returns the number of pools that were disposed.
        """
        keys_to_dispose = [k for k in self._pools if k[0] == datasource_id]
        for k in keys_to_dispose:
            entry = self._pools.pop(k, None)
            if entry is not None:
                try:
                    entry.pool.dispose()
                except Exception:
                    pass
        if keys_to_dispose:
            logger.info(
                "PoolRegistry: disposed %d pool(s) for datasource %s",
                len(keys_to_dispose), datasource_id,
            )
        return len(keys_to_dispose)

    def dispose_all(self) -> None:
        for entry in self._pools.values():
            try:
                entry.pool.dispose()
            except Exception:
                pass
        self._pools.clear()

    def snapshot(self) -> dict[str, Any]:
        return {
            "pool_count": len(self._pools),
            "total_capacity": self._total_capacity(),
            "max_pools": self._max_pools,
            "max_connections": self._max_connections,
        }


# Module-level singleton
_pool_registry: PoolRegistry | None = None


def get_pool_registry() -> PoolRegistry:
    global _pool_registry
    if _pool_registry is None:
        _pool_registry = PoolRegistry()
    return _pool_registry
