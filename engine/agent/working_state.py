"""Build the small, trusted runtime state used by policy and cancellation."""

from __future__ import annotations
from typing import Any

from sqlalchemy.orm import Session

from engine.agent.definition import AgentDefinition
from engine.agent.resource_refs import resource_refs_for_run
from engine.models import AgentRun


class RunWorkingStateAssembler:
    def __init__(
        self,
        db: Session,
        definition: AgentDefinition,
    ) -> None:
        self.db = db
        self.definition = definition

    def build(self, run: AgentRun) -> dict[str, Any]:
        resource_refs = resource_refs_for_run(self.db, run)
        state: dict[str, Any] = {
            "thread_id": str(run.session_id),
            "session_id": str(run.session_id),
            "run_id": str(run.id),
            "resource_refs": resource_refs,
            "execute": True,
            "allowed_tool_groups": list(self.definition.allowed_tool_groups),
        }
        return state
