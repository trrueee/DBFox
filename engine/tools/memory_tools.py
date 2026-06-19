"""Agent-facing memory tool handlers: search, write, delete, summarize."""

from __future__ import annotations

import logging
from typing import Any

from engine.memory.long_term_store import get_long_term_store
from engine.memory.memory_policy import is_safe_for_long_term, default_status
from engine.memory.memory_schema import MemoryRecord
from engine.memory.memory_namespace import MemoryNamespace
from engine.memory.session_memory import get_session_memory_service

logger = logging.getLogger("dbfox.memory.tools")


def memory_search(
    *,
    query: str,
    user_id: str | None = None,
    datasource_id: str | None = None,
    project_id: str | None = None,
    scope: list[str] | None = None,
    memory_types: list[str] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search long-term memory for relevant context."""
    _scope = scope or ["user", "datasource"]
    # Only include IDs whose namespace is in the requested scope.
    _eff_user = user_id if "user" in _scope else None
    _eff_project = project_id if "project" in _scope else None
    _eff_datasource = datasource_id if "datasource" in _scope else None
    namespaces = MemoryNamespace.scoped(
        user_id=_eff_user, project_id=_eff_project, datasource_id=_eff_datasource,
    )
    keywords = query.replace("?", " ").split()[:8]
    store = get_long_term_store()
    records = store.search(
        namespaces=namespaces if namespaces else None,
        types=memory_types,
        keywords=keywords,
        user_id=user_id,
        datasource_id=datasource_id,
        project_id=project_id,
        limit=limit,
    )
    return {
        "query": query,
        "memories": [
            {"id": r.id, "type": r.type, "text": r.text, "confidence": r.confidence, "source": r.source}
            for r in records
        ],
        "count": len(records),
    }


def memory_write(
    *,
    mem_type: str = "user_preference",
    text: str,
    content: dict[str, Any] | None = None,
    source: str = "user_explicit",
    user_id: str | None = None,
    datasource_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Write a memory explicitly requested by the user or confirmed by agent."""
    if not text:
        raise ValueError("text is required")
    if not is_safe_for_long_term(mem_type, source, content or {}):
        raise ValueError("Content contains forbidden patterns.")

    namespace = MemoryNamespace.user(user_id) if user_id else ()
    store = get_long_term_store()
    record = MemoryRecord(
        namespace=namespace, type=mem_type, text=text, content=content or {},
        source=source,
        confidence=1.0 if source == "user_explicit" else 0.7,
        status=default_status(mem_type, source, 1.0),
        user_id=user_id,
        datasource_id=datasource_id,
        project_id=project_id,
    )
    store.put(record)
    return {"memory_id": record.id, "type": record.type, "status": record.status}


def memory_delete(*, memory_id: str, reason: str = "user_requested") -> dict[str, Any]:
    """Delete or mark a memory as deleted."""
    store = get_long_term_store()
    ok = store.delete(memory_id)
    if not ok:
        raise ValueError(f"Memory {memory_id} not found")
    return {"memory_id": memory_id, "deleted": ok, "reason": reason}


def memory_summarize_session(*, session_id: str) -> dict[str, Any]:
    """Summarize the current session context for future recall."""
    svc = get_session_memory_service()
    mem = svc.get(session_id)

    summary_parts = []
    if mem.last_question:
        summary_parts.append(f"Last question: {mem.last_question}")
    if mem.last_sql:
        summary_parts.append(f"Last SQL: {mem.last_sql[:200]}")
    if mem.recent_artifact_ids:
        summary_parts.append(f"Artifacts generated: {len(mem.recent_artifact_ids)}")
    summary = ". ".join(summary_parts) if summary_parts else "No activity in this session."

    mem.summary = summary
    svc._cache[session_id] = mem

    return {
        "session_id": session_id, "summary": summary,
        "run_count": len(mem.recent_run_ids),
        "artifact_count": len(mem.recent_artifact_ids),
    }
