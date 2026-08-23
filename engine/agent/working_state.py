"""Build the small, trusted runtime state used by policy and cancellation."""

from __future__ import annotations
from dlcs.dbfox_data.backend.resource_kind import DATABASE_RESOURCE_KIND

from typing import Any

from sqlalchemy.orm import Session

from engine.agent.definition import AgentDefinition
from engine.agent.resource_refs import resource_refs_for_run, single_run_resource_ref
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
        resource_refs = resource_refs_for_run(self.db, run)
        database_ref = single_run_resource_ref(self.db, run, DATABASE_RESOURCE_KIND)
        datasource_id = database_ref.id if database_ref is not None else None
        datasource_generation = (
            database_ref.version or 0 if database_ref is not None else 0
        )
        datasource = self.db.get(DataSource, datasource_id) if datasource_id else None
        state: dict[str, Any] = {
            "thread_id": str(run.session_id),
            "session_id": str(run.session_id),
            "run_id": str(run.id),
            "datasource_id": datasource_id,
            "execution_id": str(run.execution_id or ""),
            "datasource_generation": datasource_generation,
            "resource_refs": resource_refs,
            "execute": True,
            "allowed_tool_groups": list(self.definition.allowed_tool_groups),
            "environment_profile": {
                "env": str(getattr(datasource, "env", "unknown")) if datasource else "unknown"
            },
        }
        return state
