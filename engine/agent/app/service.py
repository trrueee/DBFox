from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Iterator
from typing import Any, cast

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
from engine.agent_core.event_store import create_agent_event_store
from engine.agent_core.memory_projection import AgentMemoryProjectionStore

from engine.agent.graph.react_graph import build_dbfox_react_graph
from engine.agent.graph.state import DBFoxAgentState, sync_state_namespaces
from engine.agent.app.request_context import RequestContext
from engine.agent.app.response_builder import build_response

from engine.agent.app.persistence import (
    resolve_session_id,
    build_approval_checkpoint_draft,
    pending_approval_from_workspace,
    request_from_run,
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
    "environment", "schema", "db",
    "result", "chart", "answer", "sql",
]


def _runtime_error_message(exc: Exception) -> str:
    from engine.llm.errors import llm_error_from_exception

    llm_error = llm_error_from_exception(exc)
    if llm_error is not None:
        return str(llm_error)
    return f"Internal agent error: {exc}"


def _build_context_bundle(db: Session, req: AgentRunRequest) -> dict[str, Any]:
    try:
        from engine.agent_core.workspace_context import build_agent_context_bundle

        bundle = build_agent_context_bundle(db, req)
    except Exception:
        logger.warning("Failed to build agent workspace context bundle", exc_info=True)
        return {}
    return bundle if isinstance(bundle, dict) else {}


def _workspace_context_payload(
    req: AgentRunRequest,
    context_bundle: dict[str, Any],
) -> dict[str, Any] | None:
    workspace = context_bundle.get("workspace")
    if isinstance(workspace, dict):
        return workspace
    return req.workspace_context.model_dump(mode="json") if req.workspace_context else None


def _schema_context_payload(context_bundle: dict[str, Any]) -> dict[str, Any] | None:
    schema_linking = context_bundle.get("schema_linking")
    return schema_linking if isinstance(schema_linking, dict) else None


def _semantic_resolution_payload(context_bundle: dict[str, Any]) -> dict[str, Any] | None:
    semantic_context = context_bundle.get("semantic_context")
    schema_linking = context_bundle.get("schema_linking")
    payload: dict[str, Any] = {}
    if isinstance(semantic_context, dict):
        payload.update(semantic_context)
    if isinstance(schema_linking, dict):
        for key in (
            "semantic_aliases_used",
            "schema_linking_reasons",
            "selected_tables",
            "selected_columns",
        ):
            value = schema_linking.get(key)
            if value:
                payload[key] = value
    return payload or None


def _environment_context_payload(
    db: Session,
    datasource_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        from engine.environment.tools import environment_get_profile

        profile = environment_get_profile(db, datasource_id)
    except Exception:
        logger.warning(
            "Failed to build agent environment context for datasource %s",
            datasource_id,
            exc_info=True,
        )
        return None, None

    if not isinstance(profile, dict):
        return None, None
    database_map = profile.get("database_map")
    return profile, database_map if isinstance(database_map, dict) else None


def _memory_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and not item.get("__clear__")]


def _restore_session_memory(
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


def _load_session_memory_safe(memory_projection: Any, session_id: str) -> dict[str, Any] | None:
    try:
        return memory_projection.load_session_memory(session_id)
    except Exception:
        logger.warning("Failed to load agent session memory", exc_info=True)
        return None


def _list_reusable_sqls_safe(memory_projection: Any, datasource_id: str) -> list[dict[str, Any]]:
    try:
        return memory_projection.list_reusable_sqls(datasource_id=datasource_id, limit=5)
    except Exception:
        logger.warning("Failed to list datasource reusable SQL candidates", exc_info=True)
        return []


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

        emitter = self._build_emitter(run_id, session_id, 0)

        def emit(event_type: AgentRuntimeEventType, **kwargs: Any) -> AgentRuntimeEvent:
            return emitter.emit(event_type, **kwargs)

        # Start event
        yield emit(
            "agent.run.started",
            step={"datasource_id": req.datasource_id, "question": req.question, "execute": req.execute},
        )
        if self._persist_events:
            try:
                self.event_store.start_run(req, run_id=run_id, session_id=session_id)
            except Exception as exc:
                logger.warning("Failed to start persistence for run %s: %s", run_id, exc)
                self._rollback_quietly()

        # Build initial state
        initial_state = self._initial_state(req, run_id, session_id)

        # Build and run graph. The LangGraph checkpoint thread is keyed by the
        # conversation/session id so runtime memory spans turns.
        app = build_dbfox_react_graph(checkpointer=self._checkpointer)
        config = ctx.graph_config(session_id)

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
                self.event_store.cancel_run(run_id)
                self.db.commit()
            except Exception:
                self._rollback_quietly()
            yield emit("agent.run.cancelled", error="Client disconnected — run cancelled.")
            return
        except Exception as exc:
            logger.exception("Agent stream execution failed: %s", exc)
            accumulated_state["status"] = "failed"
            accumulated_state["error"] = _runtime_error_message(exc)

        # ---- after the stream loop: check for LangGraph interrupt ----------
        snapshot = app.get_state(config)
        if snapshot is not None and getattr(snapshot, "interrupts", None):
            self._flush_event_store(run_id, "approval checkpoint")
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
            if self._persist_events:
                try:
                    response.checkpoint = self.event_store.save_checkpoint(
                        run_id=run_id,
                        session_id=session_id,
                        status=draft.status,
                        current_step_name=draft.current_step_name,
                        next_step_name=draft.next_step_name,
                        plan=draft.plan,
                        state=draft.state,
                        completed_steps=draft.completed_steps,
                        pending_steps=draft.pending_steps,
                        artifacts=draft.artifacts,
                        waiting_approval_id=draft.waiting_approval_id,
                    )
                    self.db.commit()
                except Exception as exc:
                    logger.warning("Failed to persist approval checkpoint for run %s: %s", run_id, exc)
                    self._rollback_quietly()
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
        yield self._finalize_persistence(
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
            self.event_store.mark_run_resumed(run_id)
            yield emit("agent.run.resumed", step={"name": approval.step_name}, approval=approval)

        app = build_dbfox_react_graph(checkpointer=self._checkpointer)
        config = ctx.graph_config(session_id)
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
            yield from self._stream_and_merge(
                app, Command(resume=resume_value), config, accumulated_state, emit,
                agent_state, artifact_identity, emitted_artifact_ids
            )
        except GeneratorExit:
            try:
                self.event_store.cancel_run(run_id)
                self.db.commit()
            except Exception:
                self._rollback_quietly()
            yield emit("agent.run.cancelled", error="Client disconnected — run cancelled.")
            return
        except Exception as exc:
            logger.exception("Agent stream execution failed: %s", exc)
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
            self._persist_artifact_event(
                response.session_id,
                event,
                index=len(emitted_artifact_ids),
            )
            yield event
        yield self._finalize_persistence(
            emit,
            response,
            final_state=final_state,
            datasource_id=req.datasource_id,
        )

    # ---- Internal helpers ----------------------------------------------------

    def _initial_state(
        self, req: AgentRunRequest, run_id: str, session_id: str
    ) -> DBFoxAgentState:
        pending_approval = pending_approval_from_workspace(self.db, req)
        context_bundle = _build_context_bundle(self.db, req)
        context_summary = context_bundle.get("context_summary")
        environment_profile, database_map = _environment_context_payload(self.db, req.datasource_id)
        if req.execution_mode:
            execution_mode = req.execution_mode
        else:
            execution_mode = "user_requested_read" if req.execute else "suggest_only"
        clear_marker: Any = {"__clear__": True}
        state = DBFoxAgentState(
            run_id=run_id,
            thread_id=session_id,
            session_id=session_id,
            datasource_id=req.datasource_id,
            question=req.question,
            execute=req.execute,
            status="running",
            messages=[],
            workspace_context=_workspace_context_payload(req, context_bundle),
            follow_up_context=req.follow_up_context.model_dump(mode="json") if req.follow_up_context else None,
            context_summary=context_summary if isinstance(context_summary, str) else None,
            max_steps=req.max_steps,
            step_count=0,
            # ---- Progress Judge state ----
            execution_mode=execution_mode,
            allowed_tool_groups=FULL_SAFE_TOOL_GROUPS,
            progress_decision=None,
            replan_count=0,
            consecutive_blocks=0,
            # ---- Environment / Semantic layers ----
            environment_profile=environment_profile,
            database_map=database_map,
            semantic_resolution=_semantic_resolution_payload(context_bundle),
            db_search_results=None,
            db_inspection=None,
            db_preview=None,
            # ---- Large Catalog Exploration ----
            candidate_tables=[],
            searched_terms=[clear_marker],
            exhausted_paths=[clear_marker],
            # ---- Multi-query Analysis Units ----
            analysis_units=[{"__clear__": True}],
            current_analysis_unit_id=None,
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
            schema_context=_schema_context_payload(context_bundle),
            query_plan=None,
            chart_suggestion=None,
            answer=None,
            final_answer=None,
            revision_attempted=False,
            revision_count=0,
            repair_mode=False,
            repair_stats=None,
            reusable_sql_candidates=_list_reusable_sqls_safe(self.memory_projection, req.datasource_id),
        )
        _restore_session_memory(
            cast(dict[str, Any], state),
            _load_session_memory_safe(self.memory_projection, session_id),
            datasource_id=req.datasource_id,
        )
        sync_state_namespaces(cast(dict[str, Any], state))
        return state

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
        for chunk in app.stream(input_value, config=config, stream_mode=["updates", "custom"]):
            mode = "updates"
            payload = chunk
            if isinstance(chunk, tuple) and len(chunk) == 2:
                mode, payload = chunk

            if mode == "custom":
                event = self._custom_stream_event(emit, payload)
                if event is not None:
                    yield event
                continue

            if mode != "updates" or not isinstance(payload, dict):
                continue

            for node_name, update in payload.items():
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
                    context_event, last_context_summary = context_update_event(
                        emit, accumulated_state, last_context_summary,
                    )
                    if context_event is not None:
                        yield context_event

                # Emit trace events
                if "trace_events" in update:
                    for te in update["trace_events"]:
                        if isinstance(te, dict):
                            yield from trace_to_events(emit, te)

    def _custom_stream_event(self, emit: Any, payload: Any) -> AgentRuntimeEvent | None:
        if not isinstance(payload, dict) or payload.get("type") != "agent.answer.delta":
            return None
        content = payload.get("content")
        if not isinstance(content, str) or not content:
            return None
        return emit("agent.answer.delta", content=content, persist=False)

    def _merge_state(self, target: dict[str, Any], update: dict[str, Any]) -> None:
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
        sync_state_namespaces(target)

    def _build_emitter(self, run_id: str, session_id: str, start_sequence: int) -> EventEmitter:
        def save(event: AgentRuntimeEvent) -> None:
            if self._persist_events:
                try:
                    self.event_store.append_event(session_id, event)
                except Exception as exc:
                    logger.warning("Failed to persist runtime event for run %s: %s", run_id, exc)
                    self._rollback_quietly()

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
            self.event_store.append_artifact(session_id, event.run_id, event.artifact, index)
        except Exception as exc:
            logger.warning(
                "Failed to persist artifact %s for run %s: %s",
                event.artifact.id,
                event.run_id,
                exc,
            )

    def _flush_event_store(self, run_id: str, purpose: str) -> None:
        if not self._persist_events:
            return
        try:
            self.event_store.flush()
        except Exception as exc:
            logger.warning("Failed to flush event store for %s on run %s: %s", purpose, run_id, exc)
            self._rollback_quietly()

    def _persist_memory_projection(
        self,
        response: AgentRunResponse,
        *,
        final_state: dict[str, Any],
        datasource_id: str,
    ) -> None:
        self.memory_projection.save_run_projection(
            response,
            final_state=final_state,
            datasource_id=datasource_id,
        )

    def _finalize_persistence(
        self,
        emit: Any,
        response: AgentRunResponse,
        *,
        final_state: dict[str, Any] | None = None,
        datasource_id: str | None = None,
    ) -> AgentRuntimeEvent:
        if response.success:
            event = emit("agent.run.completed", response=response)
        else:
            event = emit("agent.run.failed", response=response, error=response.error)

        if self._persist_events:
            try:
                if response.success:
                    self.event_store.complete_run(response)
                    if final_state is not None and datasource_id:
                        self._persist_memory_projection(
                            response,
                            final_state=final_state,
                            datasource_id=datasource_id,
                        )
                else:
                    self.event_store.fail_run(
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


