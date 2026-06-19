"""SessionMemory service — maintains per-session context across runs.

Tracks the last question, SQL, execution, and artifacts so follow-up
requests ("export that", "revise the query", "chart the result") work
without the agent rediscovering the full schema.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from sqlalchemy.orm import Session

from engine.memory.memory_schema import SessionMemory

logger = logging.getLogger("dbfox.memory.session")


class SessionMemoryService:
    """CRUD for SessionMemory backed by in-memory dict + optional DB."""

    def __init__(self) -> None:
        self._cache: dict[str, SessionMemory] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> SessionMemory:
        with self._lock:
            if session_id not in self._cache:
                self._cache[session_id] = SessionMemory(session_id=session_id)
            return self._cache[session_id]

    def update_from_run(
        self,
        *,
        session_id: str,
        run_id: str,
        question: str,
        final_state: dict[str, Any],
        response: Any,  # AgentRunResponse
    ) -> SessionMemory:
        with self._lock:
            mem = self._cache.get(session_id)
            if mem is None:
                mem = SessionMemory(session_id=session_id)
                self._cache[session_id] = mem

            mem.last_question = question
            mem.recent_run_ids.append(run_id)
            mem.recent_run_ids = mem.recent_run_ids[-10:]

            sql = final_state.get("sql")
            if sql:
                mem.last_sql = str(sql)

            execution = final_state.get("execution")
            if isinstance(execution, dict) and execution.get("id"):
                mem.last_execution_id = str(execution.get("id"))

            artifacts = getattr(response, "artifacts", []) or []
            for art in artifacts:
                art_id = getattr(art, "id", None)
                art_type = getattr(art, "type", None)
                if not art_id:
                    continue
                mem.recent_artifact_ids.append(str(art_id))
                mem.recent_artifact_ids = mem.recent_artifact_ids[-20:]
                if art_type == "table":
                    mem.last_table_artifact_id = str(art_id)
                elif art_type == "chart":
                    mem.last_chart_artifact_id = str(art_id)
                elif art_type == "report":
                    mem.last_report_artifact_id = str(art_id)

            mem.updated_at = SessionMemory.model_fields["updated_at"].default_factory()  # type: ignore[attr-defined]

        logger.debug("SessionMemory updated: session=%s run=%s", session_id, run_id)
        return mem

    def build_context_text(self, session_id: str) -> str:
        """Return a short context block for injection into the system prompt."""
        mem = self.get(session_id)
        parts: list[str] = []
        if mem.last_question:
            parts.append(f"Last question: {mem.last_question}")
        if mem.last_sql:
            parts.append(f"Last SQL (for reference): {mem.last_sql}")
        if mem.current_topic:
            parts.append(f"Current analysis topic: {mem.current_topic}")
        if mem.current_dataset_summary:
            parts.append(f"Current dataset: {mem.current_dataset_summary}")

        if not parts:
            return ""
        return "### Session Context\n" + "\n".join(f"- {p}" for p in parts) + "\n"

    def set_topic(self, session_id: str, topic: str) -> None:
        with self._lock:
            mem = self._cache.get(session_id)
            if mem is None:
                mem = SessionMemory(session_id=session_id)
                self._cache[session_id] = mem
            mem.current_topic = topic

    def set_dataset_summary(self, session_id: str, summary: str) -> None:
        with self._lock:
            mem = self._cache.get(session_id)
            if mem is None:
                mem = SessionMemory(session_id=session_id)
                self._cache[session_id] = mem
            mem.current_dataset_summary = summary

    def set(self, session_id: str, mem: SessionMemory) -> None:
        with self._lock:
            self._cache[session_id] = mem


# Module-level singleton
_session_service: SessionMemoryService | None = None


def get_session_memory_service() -> SessionMemoryService:
    global _session_service
    if _session_service is None:
        _session_service = SessionMemoryService()
    return _session_service
