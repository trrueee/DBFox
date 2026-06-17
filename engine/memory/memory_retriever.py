"""Retrieve relevant long-term and session memories for the current run."""
from __future__ import annotations

import logging
from typing import Any

from engine.memory.long_term_store import get_long_term_store
from engine.memory.session_memory import get_session_memory_service
from engine.memory.memory_namespace import MemoryNamespace
from engine.memory.memory_schema import MemoryRecord

logger = logging.getLogger("dbfox.memory.retriever")


class MemoryRetriever:
    """Fetch relevant memories scoped to the current user/datasource/project."""

    def retrieve(
        self,
        *,
        question: str,
        datasource_id: str | None = None,
        project_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return both long-term memories and session context."""

        # Build namespaces
        namespaces = MemoryNamespace.scoped(
            user_id=user_id,
            project_id=project_id,
            datasource_id=datasource_id,
        )

        # Extract keywords from question
        keywords = _extract_keywords(question)

        store = get_long_term_store()
        memories = store.search(
            namespaces=namespaces if namespaces else None,
            user_id=user_id,
            datasource_id=datasource_id,
            project_id=project_id,
            keywords=keywords,
            limit=limit,
        )

        # Group by type
        grouped: dict[str, list[MemoryRecord]] = {}
        for m in memories:
            grouped.setdefault(m.type, []).append(m)

        # Session context
        session_text = ""
        if session_id:
            session_text = get_session_memory_service().build_context_text(session_id)

        return {
            "memories": [m.model_dump(mode="json") for m in memories],
            "grouped": {k: [m.model_dump(mode="json") for m in v] for k, v in grouped.items()},
            "session_context": session_text,
            "memory_context_text": _build_memory_context_text(grouped, session_text),
        }

    def retrieve_for_messages(
        self,
        *,
        question: str,
        datasource_id: str | None = None,
        project_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Return memory context text suitable for injection into system prompt."""
        result = self.retrieve(
            question=question,
            datasource_id=datasource_id,
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
        )
        return result["memory_context_text"]


def _build_memory_context_text(
    grouped: dict[str, list[MemoryRecord]],
    session_text: str,
) -> str:
    """Build a compact memory context block for the LLM."""
    parts: list[str] = []

    # User preferences
    prefs = grouped.get("user_preference", [])
    if prefs:
        lines = [f"- {m.text}" for m in prefs[:5]]
        parts.append("### User Preferences\n" + "\n".join(lines))

    # Project rules
    rules = grouped.get("project_rule", [])
    if rules:
        lines = [f"- {m.text}" for m in rules[:5]]
        parts.append("### Project Rules\n" + "\n".join(lines))

    # Metric definitions
    metrics = grouped.get("metric_definition", [])
    if metrics:
        lines = [f"- {m.text}" for m in metrics[:5]]
        parts.append("### Metric Definitions\n" + "\n".join(lines))

    # Schema aliases
    aliases = grouped.get("schema_alias", [])
    if aliases:
        lines = [f"- {m.text}" for m in aliases[:8]]
        parts.append("### Schema Aliases\n" + "\n".join(lines))

    # Join paths
    joins = grouped.get("join_path", [])
    if joins:
        lines = [f"- {m.text}" for m in joins[:3]]
        parts.append("### Known Join Paths\n" + "\n".join(lines))

    # Successful trajectories
    trajs = grouped.get("successful_trajectory", [])
    if trajs:
        lines = [f"- {m.text}" for m in trajs[:3]]
        parts.append("### Successful Query Patterns\n" + "\n".join(lines))

    # Failure learnings
    failures = grouped.get("failure_learning", [])
    if failures:
        lines = [f"- {m.text}" for m in failures[:3]]
        parts.append("### Lessons from Past Failures\n" + "\n".join(lines))

    # Session context
    if session_text:
        parts.append(session_text)

    if not parts:
        return ""

    return "## Relevant Context\n\n" + "\n\n".join(parts) + "\n"


def _extract_keywords(question: str) -> list[str]:
    """Extract simple keywords from a question for memory matching."""
    # Simple approach: split into words, filter short ones
    words = question.replace("?", " ").replace("，", " ").replace(",", " ").split()
    return [w.strip().lower() for w in words if len(w.strip()) > 1][:8]


# Module-level convenience
def retrieve_memory_context(
    *,
    question: str,
    datasource_id: str | None = None,
    project_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> str:
    return MemoryRetriever().retrieve_for_messages(
        question=question,
        datasource_id=datasource_id,
        project_id=project_id,
        user_id=user_id,
        session_id=session_id,
    )
