from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from engine.agent_core import persistence as agent_persistence
from engine.agent_core.types import (
    AgentRunRequest,
    AgentRunResponse,
    AgentRuntimeEvent,
    AgentRuntimeEventType,
)
from engine.errors import DBFoxError
from engine.agent_core.checkpointer import build_agent_core_checkpointer
from engine.tools.dbfox_tools import register_dbfox_tools
from engine.agent_core.artifacts import AgentArtifactIdentity
from engine.agent_core.event_store import create_agent_event_store
from engine.agent_core.memory_projection import AgentMemoryProjectionStore

from engine.agent.graph.react_graph import build_dbfox_react_graph
from engine.agent.app.request_context import RequestContext
from engine.agent.app.response_builder import build_response
from engine.agent.app.context_builder import AgentContextBuilder
from engine.agent.app.memory_projection import AgentMemoryProjectionCoordinator
from engine.agent.app.persistence_coordinator import AgentPersistenceCoordinator
from engine.agent.app.stream_runner import AgentStreamRunner
from engine.agent.app.error_boundary import public_agent_failure, safe_agent_log
from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception

from engine.agent.app.persistence import (
    resolve_session_id,
    build_approval_checkpoint_draft,
    pending_approval_from_workspace,
    request_from_run,
)
from engine.agent.app.event_mapper import (
    final_events,
    artifacts_from_state,
)

logger = logging.getLogger("dbfox.dbfox_agent.service")

def _runtime_error_message(exc: Exception) -> str:
    return public_agent_failure(exc, operation="run").message


class DBFoxAgentService:
    """Next-generation DBFox agent service built on a pure ReAct graph.

    Replaces engine.agent_kernel.service.AgentKernelService.
    """

    def __init__(self, db: Session):
        self.db = db
        self.registry = register_dbfox_tools()
        self._checkpointer = build_agent_core_checkpointer()
        _mode = os.environ.get("AGENT_PERSISTENCE_MODE", "buffered")
        _events_flag = os.environ.get("AGENT_PERSIST_RUNTIME_EVENTS", "true")
        self._persist_events = _mode != "disabled" and _events_flag.lower() != "false"
        self.event_store = create_agent_event_store(db)
        self.memory_projection = AgentMemoryProjectionStore(db)
        self.memory_projection_coordinator = AgentMemoryProjectionCoordinator(self.memory_projection)
        self.persistence_coordinator = AgentPersistenceCoordinator(
            db,
            self.event_store,
            self.memory_projection_coordinator,
            enabled=self._persist_events,
        )
        self.context_builder = AgentContextBuilder(db, self.memory_projection_coordinator)
        self.stream_runner = AgentStreamRunner(self.persistence_coordinator)

    # ---- Public API ----------------------------------------------------------

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        final_response: AgentRunResponse | None = None
        for event in self.run_iter(req):
            if event.response is not None:
                final_response = event.response
        if final_response is None:
            raise RuntimeError("DBFoxAgentService completed without a final response.")
        return final_response

    def run_iter(self, req: AgentRunRequest) -> Iterator[AgentRuntimeEvent]:
        """Stream AgentRuntimeEvents by running the ReAct graph."""
        if req.parent_run_id and not req.follow_up_context:
            req.follow_up_context = agent_persistence.build_followup_context_from_run(
                self.db, req.parent_run_id
            )

        if req.follow_up_context:
            if not req.parent_run_id:
                req.parent_run_id = req.follow_up_context.parent_run_id
            if not req.session_id:
                req.session_id = req.follow_up_context.session_id

        ctx = RequestContext(self.db, req, self.registry, self.event_store)
        run_id = str(uuid.uuid4())
        session_id = resolve_session_id(self.db, req)
        artifact_identity = AgentArtifactIdentity(run_id)

        emitter = self.persistence_coordinator.build_emitter(run_id, session_id, 0)

        def emit(event_type: AgentRuntimeEventType, **kwargs: Any) -> AgentRuntimeEvent:
            return emitter.emit(event_type, **kwargs)

        # Start event
        yield emit(
            "agent.run.started",
            step={"datasource_id": req.datasource_id, "question": req.question, "execute": req.execute},
        )
        self.persistence_coordinator.start_run(req, run_id=run_id, session_id=session_id)

        # Build initial state
        initial_state = self.context_builder.build_initial_state(
            req,
            run_id=run_id,
            session_id=session_id,
        )

        # Build and run graph. The LangGraph checkpoint thread is keyed by the
        # conversation/session id so runtime memory spans turns.
        app = build_dbfox_react_graph(checkpointer=self._checkpointer)
        config = ctx.graph_config(session_id, run_id=run_id)

        agent_state = self._new_agent_state(run_id, session_id, req)
        emitted_artifact_ids: set[str] = set()
        accumulated_state: dict[str, Any] = dict(initial_state)

        try:
            yield from self.stream_runner.stream_and_merge(
                app, initial_state, config, accumulated_state, emit,
                agent_state, artifact_identity, emitted_artifact_ids
            )
        except GeneratorExit:
            # Client disconnected (SSE stream closed by frontend cancel/abort).
            try:
                # Cancel any active SQL query on the target database so that
                # long-running queries don't keep consuming DB resources after
                # the user has abandoned the conversation.
                execution = accumulated_state.get("execution") or {}
                execution_id = execution.get("executionId") if isinstance(execution, dict) else None
                if execution_id:
                    try:
                        from engine.query_registry import QUERY_REGISTRY
                        QUERY_REGISTRY.cancel(execution_id)
                    except Exception as exc:
                        log_unexpected_exception(
                            logger,
                            operation=SafeLogOperation.AGENT_SSE_CANCEL_QUERY,
                            exc=exc,
                            level="warning",
                        )
                self.persistence_coordinator.cancel_run(run_id)
            except Exception:
                self.persistence_coordinator.rollback_quietly()
            yield emit("agent.run.cancelled", error="Client disconnected — run cancelled.")
            return
        except Exception as exc:
            safe_agent_log(logger, operation="run", exc=exc, run_id=run_id)
            accumulated_state["status"] = "failed"
            accumulated_state["error"] = _runtime_error_message(exc)

        # ---- after the stream loop: check for LangGraph interrupt ----------
        snapshot = app.get_state(config)
        if snapshot is not None and getattr(snapshot, "interrupts", None):
            self.persistence_coordinator.flush(run_id, "approval checkpoint")
            interrupt_state: dict[str, Any] = (
                dict(snapshot.values) if isinstance(snapshot.values, dict)
                else dict(accumulated_state)
            )
            draft = build_approval_checkpoint_draft(
                run_id=run_id,
                session_id=session_id,
                req=req,
                full_state=interrupt_state,
                steps=agent_state.steps,
                artifacts=artifacts_from_state(interrupt_state, agent_state),
            )
            response = draft.response
            approval = draft.approval
            checkpoint = self.persistence_coordinator.save_approval_checkpoint(
                run_id=run_id,
                session_id=session_id,
                draft=draft,
            )
            if checkpoint is not None:
                response.checkpoint = checkpoint
            if approval:
                yield emit("agent.approval.required", step={"name": approval.step_name}, approval=approval)
            yield emit("agent.checkpoint.saved", checkpoint=response.checkpoint)
            yield emit("agent.run.waiting_approval", response=response)
            return

        # ---- normal completion (no interrupt) -------------------------------
        final_state: dict[str, Any] = (
            dict(snapshot.values) if (snapshot is not None and isinstance(snapshot.values, dict))
            else dict(accumulated_state)
        )

        if final_state.get("status") == "running" or not final_state.get("status"):
            if accumulated_state.get("status") == "failed":
                final_state["status"] = "failed"
        if not final_state.get("error") and accumulated_state.get("error"):
            final_state["error"] = accumulated_state.get("error")

        success = final_state.get("status") == "completed" and not final_state.get("error")
        response = build_response(
            req=req,
            run_id=run_id,
            session_id=session_id,
            state=final_state,
            steps=agent_state.steps,
            artifacts=artifacts_from_state(final_state, agent_state),
            success=success,
            error=final_state.get("error"),
            status=final_state.get("status"),
        )

        for event in final_events(emit, response, agent_state, emitted_artifact_ids):
            self.persistence_coordinator.persist_artifact_event(
                response.session_id,
                event,
                index=len(emitted_artifact_ids),
            )
            yield event
        yield self.persistence_coordinator.finalize(
            emit,
            response,
            final_state=final_state,
            datasource_id=req.datasource_id,
        )

    def resume_approval_iter(
        self,
        *,
        run_id: str,
        approval_id: str,
        approved: bool,
        note: str | None = None,
    ) -> Iterator[AgentRuntimeEvent]:
        """Resume a graph interrupted by approval."""
        from langgraph.types import Command

        existing_approval = agent_persistence.get_approval(self.db, approval_id)
        if existing_approval is None:
            raise DBFoxError("Approval not found.", code="APPROVAL_NOT_FOUND")
        if existing_approval.run_id != run_id:
            raise DBFoxError("Approval does not belong to this run.", code="APPROVAL_RUN_MISMATCH")

        # Resolve the approval in DB.
        resolved_here = existing_approval.status == "pending"
        if resolved_here:
            approval = self.event_store.resolve_approval(
                run_id=run_id,
                approval_id=approval_id,
                decision="approved" if approved else "rejected",
                note=note,
            ) or existing_approval
        else:
            approval = existing_approval

        req = request_from_run(self.db, run_id)
        session_id = approval.session_id
        checkpoint_payload = agent_persistence.get_latest_checkpoint_payload(self.db, run_id)
        ctx = RequestContext(self.db, req, self.registry, self.event_store)

        emitter = self.persistence_coordinator.build_emitter(
            run_id, session_id,
            agent_persistence.get_latest_runtime_event_sequence(self.db, run_id),
        )

        def emit(event_type: AgentRuntimeEventType, **kwargs: Any) -> AgentRuntimeEvent:
            return emitter.emit(event_type, **kwargs)

        if resolved_here:
            yield emit(
                "agent.approval.resolved",
                step={"name": approval.step_name, "status": approval.status},
                approval=approval,
            )

        if approved:
            self.persistence_coordinator.mark_run_resumed(run_id)
            yield emit("agent.run.resumed", step={"name": approval.step_name}, approval=approval)

        app = build_dbfox_react_graph(checkpointer=self._checkpointer)
        config = ctx.graph_config(session_id, run_id=run_id)
        artifact_identity = AgentArtifactIdentity(run_id)
        agent_state = self._new_agent_state(run_id, session_id, req)
        emitted_artifact_ids: set[str] = set()
        checkpoint_state = checkpoint_payload.get("state") if isinstance(checkpoint_payload, dict) else None
        accumulated_state: dict[str, Any] = dict(checkpoint_state if isinstance(checkpoint_state, dict) else {})

        resume_value = {
            "decision": "approved" if approved else "rejected",
            "note": note or "",
        }

        try:
            yield from self.stream_runner.stream_and_merge(
                app, Command(resume=resume_value), config, accumulated_state, emit,
                agent_state, artifact_identity, emitted_artifact_ids
            )
        except GeneratorExit:
            self.persistence_coordinator.cancel_run(run_id)
            yield emit("agent.run.cancelled", error="Client disconnected — run cancelled.")
            return
        except Exception as exc:
            safe_agent_log(logger, operation="resume", exc=exc, run_id=run_id)
            accumulated_state["status"] = "failed"
            accumulated_state["error"] = _runtime_error_message(exc)

        snapshot = app.get_state(config)
        final_state: dict[str, Any] = (
            dict(snapshot.values) if isinstance(snapshot.values, dict) else dict(accumulated_state)
        )

        if not approved:
            final_state["status"] = "failed"
            final_state["error"] = "User rejected approval."

        if final_state.get("status") == "running" or not final_state.get("status"):
            if accumulated_state.get("status") == "failed":
                final_state["status"] = "failed"
        if not final_state.get("error") and accumulated_state.get("error"):
            final_state["error"] = accumulated_state.get("error")

        success = final_state.get("status") == "completed" and not final_state.get("error")
        response = build_response(
            req=req,
            run_id=run_id,
            session_id=session_id,
            state=final_state,
            steps=agent_state.steps,
            artifacts=artifacts_from_state(final_state, agent_state),
            success=success,
            error=final_state.get("error"),
            status=final_state.get("status"),
            approval=approval,
        )

        for event in final_events(emit, response, agent_state, emitted_artifact_ids):
            self.persistence_coordinator.persist_artifact_event(
                response.session_id,
                event,
                index=len(emitted_artifact_ids),
            )
            yield event
        yield self.persistence_coordinator.finalize(
            emit,
            response,
            final_state=final_state,
            datasource_id=req.datasource_id,
        )

    # ---- Internal helpers ----------------------------------------------------

    def _new_agent_state(self, run_id: str, session_id: str, req: AgentRunRequest) -> Any:
        from engine.agent_core.state import AgentState
        return AgentState(
            run_id=run_id,
            session_id=session_id,
            parent_run_id=req.parent_run_id,
            question=req.question,
            datasource_id=req.datasource_id,
        )


