from __future__ import annotations

import logging
from typing import Any

from engine.agent_core.types import AgentRunResponse
from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception

logger = logging.getLogger("dbfox.dbfox_agent.memory_projection")


class AgentMemoryProjectionCoordinator:
    """Safe adapter around the agent memory projection store."""

    def __init__(self, store: Any):
        self.store = store

    def load_session_memory(self, session_id: str) -> dict[str, Any] | None:
        try:
            return self.store.load_session_memory(session_id)
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_MEMORY_LOAD_SESSION,
                exc=exc,
                level="warning",
            )
            return None

    def list_reusable_sqls(self, datasource_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        try:
            return self.store.list_reusable_sqls(datasource_id=datasource_id, limit=limit)
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_MEMORY_LIST_REUSABLE_SQL,
                exc=exc,
                level="warning",
            )
            return []

    def save_run_projection(
        self,
        response: AgentRunResponse,
        *,
        final_state: dict[str, Any],
        datasource_id: str,
    ) -> None:
        try:
            self.store.save_run_projection(
                response,
                final_state=final_state,
                datasource_id=datasource_id,
            )
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_MEMORY_SAVE_PROJECTION,
                exc=exc,
                level="warning",
            )


def restore_session_memory(
    state: dict[str, Any],
    memory: dict[str, Any] | None,
    *,
    datasource_id: str,
) -> None:
    if not isinstance(memory, dict):
        return
    memory_datasource_id = str(memory.get("datasource_id") or "")
    if memory_datasource_id and memory_datasource_id != datasource_id:
        return

    conversation_summary = memory.get("conversation_summary")
    if isinstance(conversation_summary, str) and conversation_summary.strip():
        state["conversation_summary"] = conversation_summary

    summary_cursor_message_id = memory.get("summary_cursor_message_id")
    if isinstance(summary_cursor_message_id, str) and summary_cursor_message_id.strip():
        state["summary_cursor_message_id"] = summary_cursor_message_id

    for key in ("recent_turns", "artifact_ref_index", "sql_ref_index"):
        restored = _memory_list(memory.get(key))
        if restored:
            state[key] = restored

    active_task = memory.get("active_task")
    if isinstance(active_task, dict) and active_task:
        state["active_task"] = active_task


def _memory_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and not item.get("__clear__")]
