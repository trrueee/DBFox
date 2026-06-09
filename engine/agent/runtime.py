from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from engine.agent import persistence as agent_persistence
from engine.agent.executor import AgentStepSpec
from engine.agent.types import AgentRunRequest, AgentRunResponse, AgentRuntimeEvent
from engine.agent.context import has_follow_up_context
from engine.errors import DataBoxError


class DataBoxAgentRuntime:
    """Compatibility facade for the graph-backed Agent Kernel runtime.

    The old imperative runtime has been removed from this class. Public callers
    keep using the historical DataBoxAgentRuntime entrypoint while all control
    flow, routing, checkpointing, approvals, and tool execution are delegated to
    AgentKernelService.
    """

    def __init__(self, db: Session):
        self.db = db
        from engine.agent_kernel.service import AgentKernelService

        self.kernel = AgentKernelService(db)

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        return self._facade_response(self.kernel.run(req))

    def run_iter(self, req: AgentRunRequest) -> Iterator[AgentRuntimeEvent]:
        for event in self.kernel.run_iter(req):
            yield self._facade_event(event)

    def resume(self, run_id: str, approval_id: str | None = None) -> AgentRunResponse:
        final_response: AgentRunResponse | None = None
        for event in self.resume_iter(run_id, approval_id):
            if event.response is not None:
                final_response = event.response
        if final_response is None:
            raise RuntimeError("Agent kernel resume completed without a final response.")
        return final_response

    def resume_iter(self, run_id: str, approval_id: str | None = None) -> Iterator[AgentRuntimeEvent]:
        """Resume a resolved approval through the graph-backed kernel.

        This facade intentionally does not fail runs or commit database
        transactions. The kernel service owns approval state transitions and
        persistence side effects.
        """

        resolved_approval_id = approval_id
        if not resolved_approval_id:
            pending = agent_persistence.get_pending_approval_for_run(self.db, run_id)
            resolved_approval_id = pending.id if pending is not None else ""
        if not resolved_approval_id:
            raise DataBoxError("No approval id was supplied for resume.", code="APPROVAL_NOT_FOUND")

        approval = agent_persistence.get_approval(self.db, resolved_approval_id)
        if approval is None:
            raise DataBoxError("Approval not found.", code="APPROVAL_NOT_FOUND")
        if approval.run_id != run_id:
            raise DataBoxError("Approval does not belong to this run.", code="APPROVAL_RUN_MISMATCH")
        if approval.status == "pending":
            raise DataBoxError("Approval is still pending.", code="APPROVAL_PENDING")

        for event in self.kernel.resume_approval_iter(
            run_id=run_id,
            approval_id=resolved_approval_id,
            approved=approval.status == "approved",
        ):
            yield self._facade_event(event)

    def build_default_plan(self, request: AgentRunRequest) -> list[AgentStepSpec]:
        """Return the legacy-visible default tool order for UI/tests.

        This is metadata only. Execution no longer follows this list directly;
        the graph-backed Agent Kernel routes control flow.
        """

        steps: list[AgentStepSpec] = []
        if has_follow_up_context(request) or request.parent_run_id:
            steps.append(AgentStepSpec(name="load_follow_up_context", tool_name="followup.load_context"))
        steps.extend(
            [
                AgentStepSpec(name="build_schema_context", tool_name="schema.build_context"),
                AgentStepSpec(name="generate_sql_candidate", tool_name="sql.generate"),
                AgentStepSpec(name="validate_sql", tool_name="sql.validate"),
                AgentStepSpec(name="execute_sql", tool_name="sql.execute_readonly", required=request.execute),
                AgentStepSpec(name="profile_result", tool_name="result.profile", required=False),
                AgentStepSpec(name="suggest_chart", tool_name="chart.suggest", required=False),
                AgentStepSpec(name="suggest_followups", tool_name="followup.suggest", required=False),
                AgentStepSpec(name="answer_synthesizer", tool_name="answer.synthesize"),
            ]
        )
        return steps

    def _facade_event(self, event: AgentRuntimeEvent) -> AgentRuntimeEvent:
        if event.response is None:
            return event
        return event.model_copy(update={"response": self._facade_response(event.response)})

    def _facade_response(self, response: AgentRunResponse) -> AgentRunResponse:
        if response.success and response.status == "completed":
            return response.model_copy(update={"status": "success"})
        return response
