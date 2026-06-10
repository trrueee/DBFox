"""Extract and persist memory candidates from completed runs."""
from __future__ import annotations

import logging
from typing import Any

from engine.agent.memory.long_term_store import get_long_term_store
from engine.agent.memory.memory_policy import (
    is_safe_for_long_term,
    default_status,
)
from engine.agent.memory.memory_schema import MemoryRecord
from engine.agent.memory.memory_namespace import MemoryNamespace

logger = logging.getLogger("databox.memory.writer")


class MemoryWriter:
    """Extract candidates from final state and write to long-term store."""

    def extract_from_run(
        self,
        *,
        final_state: dict[str, Any],
        response: Any,  # AgentRunResponse
        question: str,
        run_id: str,
        session_id: str,
        datasource_id: str | None = None,
        project_id: str | None = None,
        user_id: str | None = None,
    ) -> list[MemoryRecord]:
        """Extract memory candidates from a completed run."""
        candidates: list[MemoryRecord] = []

        # 1. Successful trajectory
        if response and getattr(response, "success", False):
            traj = self._build_trajectory(final_state, question, datasource_id, run_id, session_id)
            if traj:
                candidates.append(traj)

        # 2. Failure learning
        if final_state.get("error"):
            failure = self._build_failure_learning(
                final_state, question, datasource_id, run_id, session_id
            )
            if failure:
                candidates.append(failure)

        # 3. Write candidates that pass policy
        store = get_long_term_store()
        written: list[MemoryRecord] = []
        for c in candidates:
            if not is_safe_for_long_term(c.type, c.source, c.content):
                continue
            if user_id:
                c.namespace = MemoryNamespace.user(user_id)
            if datasource_id:
                c.datasource_id = datasource_id
            if project_id:
                c.project_id = project_id
            if user_id:
                c.user_id = user_id
            c.source_run_id = run_id
            c.source_session_id = session_id
            c.status = default_status(c.type, c.source, c.confidence)
            store.put(c)
            written.append(c)

        if written:
            logger.info("MemoryWriter: wrote %d memories from run %s", len(written), run_id)
        return written

    def _build_trajectory(
        self,
        state: dict[str, Any],
        question: str,
        datasource_id: str | None,
        run_id: str,
        session_id: str,
    ) -> MemoryRecord | None:
        """Build a successful_trajectory memory."""
        tools = _extract_tools_from_state(state)
        if not tools:
            return None
        tables = _extract_tables_from_state(state)
        return MemoryRecord(
            type="successful_trajectory",
            text=f"In datasource {datasource_id}, question '{question[:80]}' "
                 f"used tools: {', '.join(tools[:5])} on tables: {', '.join(tables[:5])}.",
            content={
                "question_pattern": question[:200],
                "datasource_id": datasource_id or "",
                "tools_used": tools,
                "selected_tables": tables,
                "final_sql": state.get("sql"),
                "result_summary": _answer_summary(state),
            },
            source="trajectory_eval",
            confidence=0.7,
            source_run_id=run_id,
            source_session_id=session_id,
            datasource_id=datasource_id,
        )

    def _build_failure_learning(
        self,
        state: dict[str, Any],
        question: str,
        datasource_id: str | None,
        run_id: str,
        session_id: str,
    ) -> MemoryRecord | None:
        """Build a failure_learning memory."""
        error = state.get("error")
        if not error:
            return None
        return MemoryRecord(
            type="failure_learning",
            text=f"In datasource {datasource_id}, query failed: {str(error)[:200]}. Lesson: check SQL syntax and schema compatibility.",
            content={
                "failure_type": "execution_error",
                "error_message": str(error),
                "attempted_sql": state.get("sql"),
            },
            source="trajectory_eval",
            confidence=0.8,
            source_run_id=run_id,
            source_session_id=session_id,
            datasource_id=datasource_id,
        )


def _extract_tools_from_state(state: dict[str, Any]) -> list[str]:
    """Extract tool names from trace_events in state."""
    tools: list[str] = []
    seen: set[str] = set()
    for te in state.get("trace_events", []) or []:
        if isinstance(te, dict):
            name = te.get("tool_name")
            if name and name not in seen:
                tools.append(str(name))
                seen.add(str(name))
    return tools


def _extract_tables_from_state(state: dict[str, Any]) -> list[str]:
    """Extract table names from schema_context."""
    sc = state.get("schema_context")
    if isinstance(sc, dict):
        tables = sc.get("selected_tables") or sc.get("candidate_tables") or []
        return [str(t) for t in tables[:10] if t]
    return []


def _answer_summary(state: dict[str, Any]) -> str | None:
    """Extract a brief summary from the answer."""
    answer = state.get("answer") or state.get("final_answer")
    if isinstance(answer, dict):
        text = answer.get("answer", "")
        return text[:200] if text else None
    return None
