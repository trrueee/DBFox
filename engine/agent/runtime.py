"""DBFoxAgentRuntime — public Agent runtime facade.

This is the primary entry point for agent execution.  It delegates to
DBFoxAgentService (the LangGraph ReAct engine) while providing a
stable API for API routes, tests, and evaluation.

Dependency direction:
    engine.agent.runtime → engine.agent.app.service → engine.agent_core
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator

from sqlalchemy.orm import Session

from engine.agent_core import persistence as agent_persistence
from engine.agent_core.types import AgentRunRequest, AgentRunResponse, AgentRuntimeEvent
from engine.errors import DBFoxError

logger = logging.getLogger("dbfox.agent.runtime")


class DBFoxAgentRuntime:
    """Public Agent runtime facade backed by the DBFox ReAct agent.

    The legacy engine.agent_kernel runtime has been removed. All public callers
    use this facade, with execution delegated to DBFoxAgentService.
    """

    def __init__(self, db: Session):
        self.db = db
        from engine.agent.app.service import DBFoxAgentService

        self.kernel = DBFoxAgentService(db)

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        try:
            return self._facade_response(self.kernel.run(req))
        except DBFoxError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Agent runtime failed unexpectedly")
            raise DBFoxError(
                "Agent 运行失败，请稍后重试或查看日志。",
                code="AGENT_RUNTIME_ERROR",
            )

    def run_iter(self, req: AgentRunRequest) -> Iterator[AgentRuntimeEvent]:
        for event in self.kernel.run_iter(req):
            yield self._facade_event(event)

    def resume(self, run_id: str, approval_id: str | None = None) -> AgentRunResponse:
        final_response: AgentRunResponse | None = None
        for event in self.resume_iter(run_id, approval_id):
            if event.response is not None:
                final_response = event.response
        if final_response is None:
            raise DBFoxError("Agent resume completed without a final response.", code="AGENT_RUNTIME_ERROR")
        return final_response

    def resume_iter(self, run_id: str, approval_id: str | None = None) -> Iterator[AgentRuntimeEvent]:
        resolved_approval_id = approval_id
        if not resolved_approval_id:
            pending = agent_persistence.get_pending_approval_for_run(self.db, run_id)
            resolved_approval_id = pending.id if pending is not None else ""
        if not resolved_approval_id:
            raise DBFoxError("No approval id was supplied for resume.", code="APPROVAL_NOT_FOUND")

        approval = agent_persistence.get_approval(self.db, resolved_approval_id)
        if approval is None:
            raise DBFoxError("Approval not found.", code="APPROVAL_NOT_FOUND")
        if approval.run_id != run_id:
            raise DBFoxError("Approval does not belong to this run.", code="APPROVAL_RUN_MISMATCH")
        if approval.status == "pending":
            raise DBFoxError("Approval is still pending.", code="APPROVAL_PENDING")

        for event in self.kernel.resume_approval_iter(
            run_id=run_id,
            approval_id=resolved_approval_id,
            approved=approval.status == "approved",
        ):
            yield self._facade_event(event)

    def _facade_event(self, event: AgentRuntimeEvent) -> AgentRuntimeEvent:
        if event.response is None:
            return event
        return event.model_copy(update={"response": self._facade_response(event.response)})

    def _facade_response(self, response: AgentRunResponse) -> AgentRunResponse:
        if response.success and response.status == "completed":
            return response.model_copy(update={"status": "success"})
        return response
