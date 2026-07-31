"""Build the small, trusted runtime state used by policy and cancellation."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from engine.agent.definition import AgentDefinition
from engine.models import AgentRun, DataSource


class RunWorkingStateAssembler:
    def __init__(
        self,
        db: Session,
        definition: AgentDefinition,
    ) -> None:
        self.db = db
        self.definition = definition

    def build(self, run: AgentRun) -> dict[str, Any]:
        datasource = self.db.get(DataSource, run.datasource_id)
        state: dict[str, Any] = {
            "thread_id": str(run.session_id),
            "session_id": str(run.session_id),
            "run_id": str(run.id),
            "datasource_id": str(run.datasource_id),
            "execution_id": str(run.execution_id or ""),
            "datasource_generation": int(run.datasource_generation),
            "execute": True,
            "allowed_tool_groups": list(self.definition.allowed_tool_groups),
            "environment_profile": {
                "env": str(getattr(datasource, "env", "unknown"))
            },
        }
        return state
