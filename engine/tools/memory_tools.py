"""Agent-facing memory tool handlers: search, write, delete, summarize.

Registered into ToolRegistry so the agent can actively manage memory.
Infrastructure lives in engine.memory — zero engine.agent.* imports.
"""

from __future__ import annotations

import logging
from typing import Any

from engine.agent_core.types import ToolObservation
from engine.agent_core.tool_registry import ToolContext
from engine.memory.long_term_store import get_long_term_store
from engine.memory.memory_policy import is_safe_for_long_term, default_status
from engine.memory.memory_schema import MemoryRecord
from engine.memory.memory_namespace import MemoryNamespace
from engine.memory.session_memory import get_session_memory_service

logger = logging.getLogger("databox.memory.tools")


def memory_search(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Search long-term memory for relevant context."""
    query = str(args.get("query") or "")
    scope = args.get("scope") or ["user", "datasource"]
    memory_types = args.get("memory_types") or None

    user_id = _get_user_id(ctx)
    datasource_id = _get_datasource_id(ctx)
    project_id = _get_project_id(ctx)

    namespaces = MemoryNamespace.scoped(
        user_id=user_id,
        project_id=project_id,
        datasource_id=datasource_id,
    )

    keywords = query.replace("?", " ").split()[:8]

    store = get_long_term_store()
    records = store.search(
        namespaces=namespaces if namespaces else None,
        keywords=keywords,
        user_id=user_id,
        datasource_id=datasource_id,
        project_id=project_id,
        limit=10,
    )

    return ToolObservation(
        name="memory_search",
        status="success",
        input=args,
        output={
            "query": query,
            "memories": [
                {
                    "id": r.id,
                    "type": r.type,
                    "text": r.text,
                    "confidence": r.confidence,
                    "source": r.source,
                }
                for r in records
            ],
            "count": len(records),
        },
        latency_ms=0,
    )


def memory_write(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Write a memory explicitly requested by the user or confirmed by agent."""
    mem_type = str(args.get("type") or "user_preference")
    text = str(args.get("text") or "")
    content = args.get("content") or {}
    source = str(args.get("source") or "user_explicit")

    if not text:
        return ToolObservation(
            name="memory_write",
            status="failed",
            input=args,
            error="text is required",
            latency_ms=0,
        )

    if not is_safe_for_long_term(mem_type, source, content):
        return ToolObservation(
            name="memory_write",
            status="failed",
            input=args,
            error="Content contains forbidden patterns.",
            latency_ms=0,
        )

    user_id = _get_user_id(ctx)
    namespace = MemoryNamespace.user(user_id) if user_id else ()

    store = get_long_term_store()
    record = MemoryRecord(
        namespace=namespace,
        type=mem_type,
        text=text,
        content=content,
        source=source,
        confidence=1.0 if source == "user_explicit" else 0.7,
        status=default_status(mem_type, source, 1.0),
        user_id=user_id,
        datasource_id=_get_datasource_id(ctx),
        project_id=_get_project_id(ctx),
    )
    store.put(record)

    return ToolObservation(
        name="memory_write",
        status="success",
        input=args,
        output={
            "memory_id": record.id,
            "type": record.type,
            "status": record.status,
        },
        latency_ms=0,
    )


def memory_delete(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Delete or mark a memory as deleted."""
    memory_id = str(args.get("memory_id") or "")
    reason = str(args.get("reason") or "user_requested")

    store = get_long_term_store()
    ok = store.delete(memory_id)

    return ToolObservation(
        name="memory_delete",
        status="success" if ok else "failed",
        input=args,
        output={"memory_id": memory_id, "deleted": ok, "reason": reason},
        error=None if ok else f"Memory {memory_id} not found",
        latency_ms=0,
    )


def memory_summarize_session(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Summarize the current session context for future recall."""
    session_id = _get_session_id(ctx)
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

    return ToolObservation(
        name="summarize_session",
        status="success",
        input=args,
        output={
            "session_id": session_id,
            "summary": summary,
            "run_count": len(mem.recent_run_ids),
            "artifact_count": len(mem.recent_artifact_ids),
        },
        latency_ms=0,
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _get_user_id(ctx: ToolContext) -> str | None:
    return ctx.state_view.get("user_id") or ctx.state_view.get("thread_id")

def _get_datasource_id(ctx: ToolContext) -> str | None:
    return str(ctx.state_view.get("datasource_id") or "")

def _get_project_id(ctx: ToolContext) -> str | None:
    return ctx.state_view.get("project_id")

def _get_session_id(ctx: ToolContext) -> str:
    return str(ctx.state_view.get("thread_id") or ctx.state_view.get("session_id") or "unknown")
