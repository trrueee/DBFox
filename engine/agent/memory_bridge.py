"""Memory bridge — programmatic memory access for agent decision nodes.

This layer auto-injects memory context at key decision points:
- Planner: similar past questions, user preferences, project rules
- Progress Judge: failure recovery experience, past fixes
- Finalize: auto-write trajectory, join paths, semantic learnings

The bridge uses the same LongTermMemoryStore as the memory.* tools,
but calls it directly — no tool-call overhead, no dependency on the
model remembering to search memory.
"""

from __future__ import annotations

import logging
from typing import Any

from engine.memory.long_term_store import get_long_term_store
from engine.memory.memory_namespace import MemoryNamespace
from engine.memory.memory_schema import (
    MemoryRecord,
    SuccessfulTrajectoryContent,
    FailureLearningContent,
)

logger = logging.getLogger("databox.databox_agent.memory_bridge")

# ── Memory types relevant for auto-search ──────────────────────────────────────

_PLANNER_TYPES = [
    "user_preference",
    "project_rule",
    "successful_trajectory",
    "metric_definition",
    "schema_alias",
]

_RECOVERY_TYPES = [
    "failure_learning",
    "successful_trajectory",
]

# ── Planner context ────────────────────────────────────────────────────────────


def search_memory_for_planner(
    *,
    question: str,
    user_id: str | None = None,
    datasource_id: str | None = None,
    project_id: str | None = None,
    limit: int = 8,
) -> str:
    """Search memory for context relevant to the Planner.

    Returns a formatted string for injection into the planner prompt,
    or an empty string if nothing relevant was found.
    """
    store = get_long_term_store()

    namespaces = _build_namespaces(user_id, project_id, datasource_id)
    keywords = _extract_keywords(question)

    records = store.search(
        namespaces=namespaces,
        types=_PLANNER_TYPES,
        keywords=keywords,
        user_id=user_id,
        datasource_id=datasource_id,
        project_id=project_id,
        limit=limit,
    )

    if not records:
        return ""

    return _format_planner_memories(records)


def _format_planner_memories(records: list[MemoryRecord]) -> str:
    """Format memory records for the Planner prompt."""
    lines = ["## Relevant Memory Context"]

    grouped: dict[str, list[MemoryRecord]] = {}
    for r in records:
        grouped.setdefault(r.type, []).append(r)

    for mem_type, items in grouped.items():
        type_label = {
            "user_preference": "User Preferences",
            "project_rule": "Project Rules",
            "successful_trajectory": "Past Successful Queries",
            "metric_definition": "Metric Definitions",
            "schema_alias": "Schema Aliases",
        }.get(mem_type, mem_type)

        lines.append(f"### {type_label}")
        for item in items[:3]:
            lines.append(f"- {item.text}")
            if item.content:
                # Include key structured fields if present
                if mem_type == "successful_trajectory":
                    tables = item.content.get("selected_tables") or item.content.get("tables") or []
                    if tables:
                        lines.append(f"  (tables: {', '.join(str(t) for t in tables[:5])})")
                elif mem_type == "metric_definition":
                    expr = item.content.get("sql_expression") or item.content.get("business_definition")
                    if expr:
                        lines.append(f"  (definition: {expr})")

    return "\n".join(lines)


# ── Recovery context ───────────────────────────────────────────────────────────


def search_memory_for_recovery(
    *,
    error: str,
    failure_layer: str | None = None,
    user_id: str | None = None,
    datasource_id: str | None = None,
    project_id: str | None = None,
    limit: int = 5,
) -> str:
    """Search memory for past failure recovery experience.

    Returns a formatted string for injection into the Progress Judge prompt,
    or an empty string if nothing relevant was found.
    """
    store = get_long_term_store()

    namespaces = _build_namespaces(user_id, project_id, datasource_id)
    keywords = _extract_keywords(error)

    if failure_layer:
        keywords.append(failure_layer)

    records = store.search(
        namespaces=namespaces,
        types=_RECOVERY_TYPES,
        keywords=keywords,
        user_id=user_id,
        datasource_id=datasource_id,
        project_id=project_id,
        limit=limit,
    )

    if not records:
        return ""

    return _format_recovery_memories(records)


def _format_recovery_memories(records: list[MemoryRecord]) -> str:
    """Format memory records for the Progress Judge prompt."""
    lines = ["## Past Recovery Experience"]

    for r in records[:5]:
        if r.type == "failure_learning":
            lines.append(f"- **Lesson**: {r.text}")
            attempted = r.content.get("attempted_tool") or r.content.get("attempted_sql")
            if attempted:
                lines.append(f"  (attempted: {str(attempted)[:120]})")
        elif r.type == "successful_trajectory":
            lines.append(f"- **Past success**: {r.text}")
            tools = r.content.get("tools_used") or r.content.get("successful_tools") or []
            if tools:
                lines.append(f"  (tools used: {', '.join(str(t) for t in tools[:5])})")

    return "\n".join(lines)


# ── Trajectory writeback ──────────────────────────────────────────────────────


def write_trajectory(
    *,
    question: str,
    status: str,
    tables: list[str] | None = None,
    sql: str | None = None,
    tools_used: list[str] | None = None,
    result_summary: str | None = None,
    join_paths: list[str] | None = None,
    semantic_terms: list[dict[str, str]] | None = None,
    user_id: str | None = None,
    datasource_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """Write trajectory + learnings to long-term memory after run completion.

    Called automatically by finalize_node on successful completion.
    Idempotent — duplicate writes for the same question pattern are
    deduplicated by the store's upsert semantics.
    """
    store = get_long_term_store()
    namespace = MemoryNamespace.user(user_id) if user_id else ()

    # ── 1. Successful trajectory ────────────────────────────────────────
    if status == "completed":
        trajectory_text = f"Question: {question[:200]}"
        if tables:
            trajectory_text += f" | Tables: {', '.join(tables[:8])}"
        if result_summary:
            trajectory_text += f" | Result: {result_summary[:200]}"

        record = MemoryRecord(
            namespace=namespace,
            type="successful_trajectory",
            text=trajectory_text,
            content={
                "question_pattern": question[:300],
                "tables": tables or [],
                "selected_tables": tables or [],
                "final_sql": sql,
                "tools_used": tools_used or [],
                "successful_tools": tools_used or [],
                "result_summary": result_summary,
                "sql_shape": _classify_sql_shape(sql) if sql else None,
            },
            source="system_generated",
            confidence=0.8,
            status="active",
            user_id=user_id,
            datasource_id=datasource_id,
            project_id=project_id,
            source_run_id=run_id,
            source_session_id=session_id,
        )
        store.put(record)
        logger.info("Trajectory written: %s", trajectory_text[:100])

    # ── 2. Join path learnings ──────────────────────────────────────────
    if join_paths:
        for jp in join_paths[:3]:
            store.put(MemoryRecord(
                namespace=namespace,
                type="join_path",
                text=f"Join path: {jp}",
                content={"join_path": jp, "datasource_id": datasource_id or ""},
                source="system_generated",
                confidence=0.7,
                status="active",
                user_id=user_id,
                datasource_id=datasource_id,
                project_id=project_id,
                source_run_id=run_id,
                source_session_id=session_id,
            ))

    # ── 3. Semantic term learnings ──────────────────────────────────────
    if semantic_terms:
        for st in semantic_terms[:5]:
            term = st.get("term", "")
            mapping = st.get("mapping", "")
            if term and mapping:
                store.put(MemoryRecord(
                    namespace=namespace,
                    type="metric_definition",
                    text=f"{term} → {mapping}",
                    content={"metric_name": term, "business_definition": mapping},
                    source="system_generated",
                    confidence=0.6,
                    status="pending_review",
                    user_id=user_id,
                    datasource_id=datasource_id,
                    project_id=project_id,
                    source_run_id=run_id,
                    source_session_id=session_id,
                ))

    # ── 4. Failure learning ─────────────────────────────────────────────
    if status == "failed":
        failure_text = f"Question: {question[:200]}"
        store.put(MemoryRecord(
            namespace=namespace,
            type="failure_learning",
            text=failure_text,
            content={
                "failure_type": "execution_failure",
                "question_pattern": question[:300],
                "attempted_sql": sql,
            },
            source="system_generated",
            confidence=0.7,
            status="active",
            user_id=user_id,
            datasource_id=datasource_id,
            project_id=project_id,
            source_run_id=run_id,
            source_session_id=session_id,
        ))


# ── Helpers ────────────────────────────────────────────────────────────────────


def _build_namespaces(
    user_id: str | None,
    project_id: str | None,
    datasource_id: str | None,
) -> list[tuple[str, ...]]:
    return MemoryNamespace.scoped(
        user_id=user_id,
        project_id=project_id,
        datasource_id=datasource_id,
    )


def _extract_keywords(text: str, max_kw: int = 8) -> list[str]:
    """Extract simple keyword tokens from text for memory search."""
    # Remove common stopwords and punctuation
    stopwords = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "can", "could", "may", "might", "shall", "should", "i", "you",
        "he", "she", "it", "we", "they", "me", "him", "her", "us",
        "them", "my", "your", "his", "its", "our", "their", "this",
        "that", "these", "those", "what", "which", "who", "whom",
        "how", "when", "where", "why", "and", "or", "not", "but",
        "in", "on", "at", "to", "for", "of", "from", "with", "by",
        "about", "as", "into", "through", "during", "before", "after",
    }
    words = text.lower().replace("?", " ").replace(",", " ").replace(".", " ").split()
    return [w for w in words if w not in stopwords and len(w) > 1][:max_kw]


def _classify_sql_shape(sql: str) -> str | None:
    """Classify SQL into a rough shape category."""
    s = sql.strip().upper()
    if s.startswith("SELECT"):
        if "GROUP BY" in s:
            return "group_by_aggregation"
        if "JOIN" in s:
            return "multi_table_join"
        if "WHERE" in s:
            return "filtered_select"
        return "simple_select"
    return None
