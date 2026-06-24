"""DBFox memory utilities.

Runtime memory lives in graph state plus the persisted projection/global SQL
stores. This package only exposes deterministic context compaction helpers.
"""

from engine.memory.memory_compactor import (
    MemoryCompactionConfig,
    compact_execution_result,
    compact_messages,
    compact_schema_context,
)

__all__ = [
    "MemoryCompactionConfig",
    "compact_execution_result",
    "compact_messages",
    "compact_schema_context",
]
