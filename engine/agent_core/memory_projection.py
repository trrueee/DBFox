from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from engine.agent_core import persistence as agent_persistence


class AgentMemoryProjectionStore:
    def __init__(self, db: Session) -> None:
        self.db = db

    def load_session_memory(self, session_id: str) -> dict[str, Any] | None:
        return agent_persistence.load_session_memory(self.db, session_id)

    def list_reusable_sqls(self, *, datasource_id: str, limit: int = 5) -> list[dict[str, Any]]:
        return agent_persistence.list_reusable_sqls(
            self.db,
            datasource_id=datasource_id,
            limit=limit,
        )

    def save_run_projection(
        self,
        response: Any,
        *,
        final_state: dict[str, Any],
        datasource_id: str,
    ) -> None:
        artifact_refs = _memory_list(final_state.get("artifact_ref_index"))
        sql_refs = _memory_list(final_state.get("sql_ref_index"))
        recent_turns = _memory_list(final_state.get("recent_turns"))

        payload: dict[str, Any] = {
            "session_id": response.session_id,
            "datasource_id": datasource_id,
            "last_run_id": response.run_id,
            "conversation_summary": final_state.get("conversation_summary") or response.context_summary,
            "summary_cursor_message_id": final_state.get("summary_cursor_message_id"),
            "recent_turns": recent_turns,
            "artifact_ref_index": artifact_refs,
            "sql_ref_index": sql_refs,
            "active_task": final_state.get("active_task"),
        }
        agent_persistence.save_session_memory(
            self.db,
            session_id=response.session_id,
            datasource_id=datasource_id,
            payload=payload,
        )

        for ref in sql_refs:
            safe_sql = str(ref.get("safe_sql") or "").strip()
            ref_datasource_id = str(ref.get("datasource_id") or datasource_id)
            if not safe_sql or not ref_datasource_id:
                continue
            agent_persistence.upsert_reusable_sql(
                self.db,
                datasource_id=ref_datasource_id,
                question=str(ref.get("question") or response.question),
                safe_sql=safe_sql,
                purpose=ref.get("purpose"),
                involved_tables=list(ref.get("tables") or ref.get("involved_tables") or []),
                result_columns=list(ref.get("columns") or ref.get("result_columns") or []),
                source_artifact_id=ref.get("artifact_id"),
                source_sql_artifact_id=ref.get("source_sql_artifact_id"),
                verified=bool(ref.get("verified")),
            )


def _memory_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and not item.get("__clear__")]
