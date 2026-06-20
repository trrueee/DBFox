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
from engine.agent_core.events import EventEmitter

from engine.agent.graph.react_graph import build_dbfox_react_graph
from engine.agent.graph.state import DBFoxAgentState
from engine.agent.app.request_context import RequestContext
from engine.agent.app.response_builder import build_response

from engine.agent.app.persistence import (
    resolve_session_id,
    start_run_persistence,
    pending_approval_from_workspace,
    request_from_run,
    save_approval_checkpoint,
)
from engine.agent.app.event_mapper import (
    observe_events,
    trace_to_events,
    context_update_event,
    final_events,
    artifacts_from_state,
)

logger = logging.getLogger("dbfox.dbfox_agent.service")

# Full set of safe tool groups available to the model on every run.
# The policy gate and execution_mode control what actually executes.
FULL_SAFE_TOOL_GROUPS = [
    "environment", "schema", "db", "memory",
    "result", "chart", "answer", "sql",
]


class DBFoxAgentService:
    """Next-generation DBFox agent service built on a pure ReAct graph.

    Replaces engine.agent_kernel.service.AgentKernelService.
    """

    def __init__(self, db: Session):
        self.db = db
        self.registry = register_dbfox_tools()
        self._checkpointer = build_agent_core_checkpointer()
        _mode = os.environ.get("AGENT_PERSISTENCE_MODE", "sync")
        _events_flag = os.environ.get("AGENT_PERSIST_RUNTIME_EVENTS", "true")
        self._persist_events = _mode != "disabled" and _events_flag.lower() != "false"
        from engine.agent_core.persistence_sink import create_persistence_sink
        self.persistence_sink = create_persistence_sink(db)

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

        ctx = RequestContext(self.db, req, self.registry)
        run_id = str(uuid.uuid4())
        session_id = resolve_session_id(self.db, req)
        artifact_identity = AgentArtifactIdentity(run_id)

        emitter = self._build_emitter(run_id, session_id, 0)

        def emit(event_type: AgentRuntimeEventType, **kwargs: Any) -> AgentRuntimeEvent:
            return emitter.emit(event_type, **kwargs)

        # Start event
        yield emit(
            "agent.run.started",
            step={"datasource_id": req.datasource_id, "question": req.question, "execute": req.execute},
        )
        if self._persist_events:
            start_run_persistence(self.persistence_sink, req, run_id, session_id, self.db)

        # Build initial state
        initial_state = self._initial_state(req, run_id, session_id)

        # Build and run graph. The LangGraph checkpoint thread is keyed by
        # run_id (not session_id).
        app = build_dbfox_react_graph(checkpointer=self._checkpointer)
        config = ctx.graph_config(run_id)

        agent_state = self._new_agent_state(run_id, session_id, req)
        emitted_artifact_ids: set[str] = set()
        accumulated_state: dict[str, Any] = dict(initial_state)

        try:
            yield from self._stream_and_merge(
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
                    except Exception:
                        logger.debug("Failed to cancel active SQL query on SSE disconnect", exc_info=True)
                agent_persistence.cancel_run(self.db, run_id=run_id)
                self.db.commit()
            except Exception:
                self._rollback_quietly()
            yield emit("agent.run.cancelled", error="Client disconnected — run cancelled.")
            return
        except Exception as exc:
            logger.exception("Agent stream execution failed: %s", exc)
            accumulated_state["status"] = "failed"
            accumulated_state["error"] = f"Internal agent error: {exc}"

        # ---- after the stream loop: check for LangGraph interrupt ----------
        snapshot = app.get_state(config)
        if snapshot is not None and getattr(snapshot, "interrupts", None):
            interrupt_state: dict[str, Any] = (
                dict(snapshot.values) if isinstance(snapshot.values, dict)
                else dict(accumulated_state)
            )
            response, approval = save_approval_checkpoint(
                self.db,
                run_id=run_id,
                session_id=session_id,
                req=req,
                full_state=interrupt_state,
                steps=agent_state.steps,
                artifacts=artifacts_from_state(interrupt_state, agent_state),
            )
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
            self._persist_artifact_event(
                response.session_id,
                event,
                index=len(emitted_artifact_ids),
            )
            yield event
        yield self._finalize_persistence(emit, response)

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
            approval = agent_persistence.resolve_approval(
                self.db,
                run_id=run_id,
                approval_id=approval_id,
                decision="approved" if approved else "rejected",
                note=note,
            )
        else:
            approval = existing_approval

        req = request_from_run(self.db, run_id)
        session_id = approval.session_id
        checkpoint_payload = agent_persistence.get_latest_checkpoint_payload(self.db, run_id)
        ctx = RequestContext(self.db, req, self.registry)

        emitter = self._build_emitter(
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
            agent_persistence.mark_run_resumed(self.db, run_id=run_id)
            yield emit("agent.run.resumed", step={"name": approval.step_name}, approval=approval)

        app = build_dbfox_react_graph(checkpointer=self._checkpointer)
        config = ctx.graph_config(run_id)
        artifact_identity = AgentArtifactIdentity(run_id)
        agent_state = self._new_agent_state(run_id, session_id, req)
        emitted_artifact_ids: set[str] = set()
        accumulated_state: dict[str, Any] = dict(checkpoint_payload.get("state") or {})

        resume_value = {
            "decision": "approved" if approved else "rejected",
            "note": note or "",
        }

        try:
            yield from self._stream_and_merge(
                app, Command(resume=resume_value), config, accumulated_state, emit,
                agent_state, artifact_identity, emitted_artifact_ids
            )
        except GeneratorExit:
            try:
                agent_persistence.cancel_run(self.db, run_id=run_id)
                self.db.commit()
            except Exception:
                self._rollback_quietly()
            yield emit("agent.run.cancelled", error="Client disconnected — run cancelled.")
            return
        except Exception as exc:
            logger.exception("Agent stream execution failed: %s", exc)
            accumulated_state["status"] = "failed"
            accumulated_state["error"] = f"Internal agent error: {exc}"

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
            self._persist_artifact_event(
                response.session_id,
                event,
                index=len(emitted_artifact_ids),
            )
            yield event
        yield self._finalize_persistence(emit, response)

    # ---- Internal helpers ----------------------------------------------------

    def _initial_state(
        self, req: AgentRunRequest, run_id: str, session_id: str
    ) -> DBFoxAgentState:
        pending_approval = pending_approval_from_workspace(self.db, req)
        if req.execution_mode:
            execution_mode = req.execution_mode
        else:
            execution_mode = "user_requested_read" if req.execute else "suggest_only"
        return DBFoxAgentState(
            run_id=run_id,
            thread_id=session_id,
            datasource_id=req.datasource_id,
            execute=req.execute,
            status="running",
            messages=[{"role": "user", "content": req.question}],
            workspace_context=req.workspace_context.model_dump(mode="json") if req.workspace_context else None,
            follow_up_context=req.follow_up_context.model_dump(mode="json") if req.follow_up_context else None,
            max_steps=req.max_steps,
            step_count=0,
            # ---- Progress Judge state ----
            execution_mode=execution_mode,
            allowed_tool_groups=FULL_SAFE_TOOL_GROUPS,
            progress_decision=None,
            replan_count=0,
            consecutive_blocks=0,
            # ---- Environment / Semantic layers ----
            environment_profile=None,
            database_map=None,
            semantic_resolution=None,
            db_search_results=None,
            db_inspection=None,
            db_preview=None,
            # ---- Large Catalog Exploration ----
            candidate_tables=[],
            searched_terms=[{"__clear__": True}],
            exhausted_paths=[{"__clear__": True}],
            # ---- Tool-call / policy routing ----
            pending_tool_calls=[],
            allowed_tool_calls=[],
            blocked_tool_calls=[],
            last_tool_results=[],
            artifacts=[{"__clear__": True}],
            trace_events=[{"__clear__": True}],
            runtime_events=[{"__clear__": True}],
            plan_events=[{"__clear__": True}],
            suggestions=[{"__clear__": True}],
            tool_call_history=[{"__clear__": True}],
            error=None,
            pending_approval=pending_approval,
            parent_run_id=req.parent_run_id,
            sql=None,
            safety=None,
            execution=None,
            schema_context=None,
            query_plan=None,
            result_profile=None,
            chart_suggestion=None,
            answer=None,
            final_answer=None,
            revision_attempted=False,
            revision_count=0,
            repair_mode=False,
            repair_stats=None,
        )

    def _new_agent_state(self, run_id: str, session_id: str, req: AgentRunRequest) -> Any:
        from engine.agent_core.state import AgentState
        return AgentState(
            run_id=run_id,
            session_id=session_id,
            parent_run_id=req.parent_run_id,
            question=req.question,
            datasource_id=req.datasource_id,
        )

    def _stream_and_merge(
        self,
        app: Any,
        input_value: Any,
        config: Any,
        accumulated_state: dict[str, Any],
        emit: Any,
        agent_state: Any,
        artifact_identity: Any,
        emitted_artifact_ids: set[str],
    ) -> Iterator[AgentRuntimeEvent]:
        last_context_summary = ""
        for chunk in app.stream(input_value, config=config, stream_mode="updates"):
            for node_name, update in chunk.items():
                if not isinstance(update, dict):
                    continue

                self._merge_state(accumulated_state, update)
                node_str = str(node_name)

                # Emit artifacts from observe node
                if node_str == "observe":
                    for event in observe_events(
                        emit, update, agent_state, artifact_identity, emitted_artifact_ids
                    ):
                        self._persist_artifact_event(
                            agent_state.session_id,
                            event,
                            index=len(emitted_artifact_ids),
                        )
                        yield event

                if node_str in ("observe", "progress", "repair"):
                    event, last_context_summary = context_update_event(
                        emit, accumulated_state, last_context_summary,
                    )
                    if event is not None:
                        yield event

                # Emit trace events
                if "trace_events" in update:
                    for te in update["trace_events"]:
                        if isinstance(te, dict):
                            yield from trace_to_events(emit, te)

    def _merge_state(self, target: dict[str, Any], update: dict[str, Any]) -> None:
        from engine.agent.graph.state import DBFoxAgentState
        from typing import get_origin, get_args
        import typing

        if not hasattr(self, "_list_keys"):
            list_keys = set()
            for key, ann in DBFoxAgentState.__annotations__.items():
                origin = get_origin(ann)
                if origin is list or ann is list:
                    list_keys.add(key)
                elif origin is typing.Annotated or (hasattr(typing, "_AnnotatedAlias") and isinstance(ann, typing._AnnotatedAlias)):
                    args = get_args(ann)
                    if args and (get_origin(args[0]) is list or args[0] is list):
                        list_keys.add(key)
            self._list_keys = list_keys

        # Routing list keys that should use replace semantics
        replace_keys = {
            "allowed_tool_calls",
            "blocked_tool_calls",
            "pending_tool_calls",
            "last_tool_results",
            "allowed_tool_groups",
        }

        for key, value in update.items():
            if key in self._list_keys and key not in replace_keys:
                if isinstance(value, list):
                    if value and isinstance(value[0], dict) and value[0].get("__clear__"):
                        target[key] = list(value[1:])
                    else:
                        target.setdefault(key, []).extend(value)
                continue
            
            # Deep-merge dict fields so that nested keys from earlier chunks
            # are not overwritten by later partial updates (e.g. environment_profile
            # built incrementally across observe and progress nodes).
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                target[key] = {**target[key], **value}
            else:
                target[key] = value

    def _build_emitter(self, run_id: str, session_id: str, start_sequence: int) -> EventEmitter:
        def save(event: AgentRuntimeEvent) -> None:
            if self._persist_events:
                self.persistence_sink.record_event(session_id, event)

        return EventEmitter(run_id, save, start_sequence=start_sequence)

    def _persist_artifact_event(
        self,
        session_id: str,
        event: AgentRuntimeEvent,
        *,
        index: int,
    ) -> None:
        if (
            not self._persist_events
            or event.type != "agent.artifact.created"
            or event.artifact is None
        ):
            return
        try:
            self.persistence_sink.record_artifact(session_id, event.run_id, event.artifact, index)
        except Exception as exc:
            logger.warning(
                "Failed to persist artifact %s for run %s: %s",
                event.artifact.id,
                event.run_id,
                exc,
            )

    def _finalize_persistence(
        self, emit: Any, response: AgentRunResponse
    ) -> AgentRuntimeEvent:
        if response.success:
            event = emit("agent.run.completed", response=response)
        else:
            event = emit("agent.run.failed", response=response, error=response.error)

        if self._persist_events:
            try:
                if response.success:
                    self.persistence_sink.complete_run(response)
                else:
                    self.persistence_sink.fail_run(
                        response.run_id, response.session_id,
                        response.error or response.status or "Agent stopped.", response,
                    )
                self.db.commit()
            except Exception as exc:
                logger.warning("Failed to persist final response for run %s: %s", response.run_id, exc)
                self._rollback_quietly()

        return event

    def _rollback_quietly(self) -> None:
        try:
            self.db.rollback()
        except Exception:
            pass


