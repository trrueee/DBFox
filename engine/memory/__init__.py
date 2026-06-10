"""DataBox Memory Layer — three-tier memory architecture.

  ShortTermMemory  — LangGraph thread state (checkpointer-backed)
  SessionMemory    — within-session runs, artifacts, SQL context
  LongTermMemory   — cross-session user prefs, project rules, schema aliases, trajectories

This is an independent infrastructure package.  It has NO dependency on
engine.agent (runtime) or engine.agent_core.
"""

from engine.memory.memory_schema import (
    MemoryRecord,
    MemoryType,
    MemorySource,
    MemoryStatus,
    SessionMemory,
    UserPreferenceContent,
    MetricDefinitionContent,
    SchemaAliasContent,
    JoinPathContent,
    SuccessfulTrajectoryContent,
    FailureLearningContent,
)
from engine.memory.long_term_store import get_long_term_store, LongTermMemoryStore
from engine.memory.session_memory import get_session_memory_service, SessionMemoryService
from engine.memory.memory_namespace import MemoryNamespace
from engine.memory.memory_policy import is_safe_for_long_term, default_status
from engine.memory.memory_retriever import MemoryRetriever
from engine.memory.memory_writer import MemoryWriter
from engine.memory.memory_compactor import compact_messages, compact_schema_context, compact_execution_result, MemoryCompactionConfig

__all__ = [
    "FailureLearningContent",
    "JoinPathContent",
    "LongTermMemoryStore",
    "MemoryCompactionConfig",
    "MemoryNamespace",
    "MemoryRecord",
    "MemoryRetriever",
    "MemorySource",
    "MemoryStatus",
    "MemoryType",
    "MemoryWriter",
    "MetricDefinitionContent",
    "SchemaAliasContent",
    "SessionMemory",
    "SessionMemoryService",
    "SuccessfulTrajectoryContent",
    "UserPreferenceContent",
    "compact_execution_result",
    "compact_messages",
    "compact_schema_context",
    "default_status",
    "get_long_term_store",
    "get_session_memory_service",
    "is_safe_for_long_term",
]
