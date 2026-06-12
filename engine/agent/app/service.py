from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from engine.agent_core import persistence as agent_persistence
from engine.agent_core.types import (
    AgentApprovalRecord,
    AgentAnswer,
    AgentArtifact,
    AgentCheckpointRecord,
    AgentRunRequest,
    AgentRunResponse,
    AgentRuntimeEvent,
    AgentRuntimeEventType,
    AgentStep,
)
from engine.errors import DataBoxError
from engine.models import AgentRun
from engine.agent_core.checkpointer import build_agent_kernel_checkpointer
from engine.tools.databox_tools import register_databox_tools
from engine.agent_core.artifacts import AgentArtifactIdentity
from engine.agent_core.events import EventEmitter

from engine.agent.graph.react_graph import build_databox_react_graph
from engine.agent.graph.state import DataBoxAgentState
from engine.agent.app.request_context import RequestContext
from engine.agent.app.response_builder import build_response

logger = logging.getLogger("databox.databox_agent.service")

# Full set of safe tool groups available to the model on every run.
# The policy gate and execution_mode control what actually executes.
FULL_SAFE_TOOL_GROUPS = [
    "workspace", "environment", "schema", "db", "semantic", "memory",
]


class DataBoxAgentService:
    """Next-generation DataBox agent service built on a pure ReAct graph.

    Replaces engine.agent_kernel.service.AgentKernelService.
    """

    def __init__(self, db: Session):
        self.db = db
        self.registry = register_databox_tools()
        self._checkpointer = build_agent_kernel_checkpointer()
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
            raise RuntimeError("DataBoxAgentService completed without a final response.")
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
        session_id = self._session_id(req)
        artifact_identity = AgentArtifactIdentity(run_id)

        emitter = self._build_emitter(run_id, session_id, 0)

        def emit(event_type: AgentRuntimeEventType, **kwargs: Any) -> AgentRuntimeEvent:
            return emitter.emit(event_type, **kwargs)

        # Start event
        yield emit(
            "agent.run.started",
            step={"datasource_id": req.datasource_id, "question": req.question, "execute": req.execute},
        )
        self._start_persistence(req, run_id, session_id)

        # Build initial state
        initial_state = self._initial_state(req, run_id, session_id)

        # Build and run graph. The LangGraph checkpoint thread is keyed by
        # run_id (not session_id): each run starts from a fresh thread, and
        # conversation continuity is provided via follow_up_context. Keying by
        # session would leak prior runs' messages into new runs, bloating the
        # context window and causing timeouts on multi-turn conversations.
        app = build_databox_react_graph(checkpointer=self._checkpointer)
        config = ctx.graph_config(run_id)

        agent_state = self._new_agent_state(run_id, session_id, req)
        emitted_artifact_ids: set[str] = set()
        accumulated_state: dict[str, Any] = dict(initial_state)
        last_context_summary = ""

        try:
            for chunk in app.stream(initial_state, config=config, stream_mode="updates"):
                for node_name, update in chunk.items():
                    if not isinstance(update, dict):
                        continue

                    self._merge_state(accumulated_state, update)
                    node_str = str(node_name)

                    # Emit artifacts from observe node
                    if node_str == "observe":
                        yield from self._observe_events(
                            emit, update, agent_state, artifact_identity, emitted_artifact_ids
                        )

                    if node_str in ("observe", "progress", "repair"):
                        event, last_context_summary = self._context_update_event(
                            emit, accumulated_state, last_context_summary,
                        )
                        if event is not None:
                            yield event

                    # Emit trace events (including approval-related traffic
                    # that the approval_node emits before/after interrupt())
                    if "trace_events" in update:
                        for te in update["trace_events"]:
                            if isinstance(te, dict):
                                yield from self._trace_to_events(emit, te)
        except GeneratorExit:
            # Client disconnected (SSE stream closed by frontend cancel/abort).
            # Mark the run as cancelled and exit cleanly — no traceback.
            try:
                agent_persistence.cancel_run(self.db, run_id=run_id)
                self.db.commit()
            except Exception:
                self._rollback_quietly()
            yield emit("agent.run.cancelled", error="Client disconnected — run cancelled.")
            return

        # ---- after the stream loop: check for LangGraph interrupt ----------
        # The graph may have been paused by approval_interrupt() calling
        # interrupt().  We detect this via snapshot.interrupts rather than
        # inspecting per-node updates, because the approval node never
        # returns a normal update — it suspends mid-execution.
        snapshot = app.get_state(config)
        if snapshot is not None and getattr(snapshot, "interrupts", None):
            # Graph was paused for human approval — persist the FULL state
            # (not just the last policy update) so resume has everything.
            interrupt_state: dict[str, Any] = (
                dict(snapshot.values) if isinstance(snapshot.values, dict)
                else dict(accumulated_state)
            )
            yield from self._approval_events(
                emit, interrupt_state, agent_state, run_id, session_id, req
            )
            return

        # ---- normal completion (no interrupt) -------------------------------
        final_state: dict[str, Any] = (
            dict(snapshot.values) if (snapshot is not None and isinstance(snapshot.values, dict))
            else dict(accumulated_state)
        )

        success = final_state.get("status") == "completed" and not final_state.get("error")
        response = build_response(
            req=req,
            run_id=run_id,
            session_id=session_id,
            state=final_state,
            steps=agent_state.steps,
            artifacts=self._artifacts_from_state(final_state, agent_state),
            success=success,
            error=final_state.get("error"),
            status=final_state.get("status"),
        )

        yield from self._final_events(emit, response, agent_state, emitted_artifact_ids)
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
            raise DataBoxError("Approval not found.", code="APPROVAL_NOT_FOUND")
        if existing_approval.run_id != run_id:
            raise DataBoxError("Approval does not belong to this run.", code="APPROVAL_RUN_MISMATCH")

        # Resolve the approval in DB. If it was already resolved (e.g. via the
        # approvals API) we skip both resolution and the approval.resolved event.
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

        req = self._request_from_run(run_id)
        session_id = approval.session_id
        checkpoint_payload = agent_persistence.get_latest_checkpoint_payload(self.db, run_id)
        ctx = RequestContext(self.db, req, self.registry)

        emitter = self._build_emitter(
            run_id, session_id,
            agent_persistence.get_latest_runtime_event_sequence(self.db, run_id),
        )

        def emit(event_type: AgentRuntimeEventType, **kwargs: Any) -> AgentRuntimeEvent:
            return emitter.emit(event_type, **kwargs)

        # Emit approval resolved (only when this call performed the resolution)
        if resolved_here:
            yield emit(
                "agent.approval.resolved",
                step={"name": approval.step_name, "status": approval.status},
                approval=approval,
            )

        if approved:
            agent_persistence.mark_run_resumed(self.db, run_id=run_id)
            yield emit("agent.run.resumed", step={"name": approval.step_name}, approval=approval)

        app = build_databox_react_graph(checkpointer=self._checkpointer)
        # Same thread key as run_iter — the interrupted checkpoint lives under run_id.
        config = ctx.graph_config(run_id)
        artifact_identity = AgentArtifactIdentity(run_id)
        agent_state = self._new_agent_state(run_id, session_id, req)
        emitted_artifact_ids: set[str] = set()
        accumulated_state: dict[str, Any] = dict(checkpoint_payload.get("state") or {})

        resume_value = {
            "decision": "approved" if approved else "rejected",
            "note": note or "",
        }

        for chunk in app.stream(
            Command(resume=resume_value), config=config, stream_mode="updates"
        ):
            for node_name, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                self._merge_state(accumulated_state, update)
                node_str = str(node_name)

                if node_str == "observe":
                    yield from self._observe_events(
                        emit, update, agent_state, artifact_identity, emitted_artifact_ids
                    )
                if "trace_events" in update:
                    for te in update["trace_events"]:
                        if isinstance(te, dict):
                            yield from self._trace_to_events(emit, te)

        snapshot = app.get_state(config)
        final_state: dict[str, Any] = (
            dict(snapshot.values) if isinstance(snapshot.values, dict) else dict(accumulated_state)
        )

        if not approved:
            final_state["status"] = "failed"
            final_state["error"] = "User rejected approval."

        success = final_state.get("status") == "completed" and not final_state.get("error")
        response = build_response(
            req=req,
            run_id=run_id,
            session_id=session_id,
            state=final_state,
            steps=agent_state.steps,
            artifacts=self._artifacts_from_state(final_state, agent_state),
            success=success,
            error=final_state.get("error"),
            status=final_state.get("status"),
            approval=approval,
        )

        yield from self._final_events(emit, response, agent_state, emitted_artifact_ids)
        yield self._finalize_persistence(emit, response)

    # ---- Internal helpers ----------------------------------------------------

    def _initial_state(
        self, req: AgentRunRequest, run_id: str, session_id: str
    ) -> DataBoxAgentState:
        pending_approval = self._pending_approval_from_workspace(req)
        # Derive execution_mode from the new field or fall back to execute bool
        if req.execution_mode:
            execution_mode = req.execution_mode
        else:
            execution_mode = "user_requested_read" if req.execute else "suggest_only"
        return DataBoxAgentState(
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
             # ---- Tool-call / policy routing ----
            pending_tool_calls=[],
            allowed_tool_calls=[],
            blocked_tool_calls=[],
            last_tool_results=[],
            artifacts=[{"__clear__": True}],
            trace_events=[{"__clear__": True}],
            runtime_events=[{"__clear__": True}],
            plan_events=[{"__clear__": True}],
            suggestions=[],
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

    def _merge_state(self, target: dict[str, Any], update: dict[str, Any]) -> None:
        for key, value in update.items():
            if key in ("messages", "artifacts", "trace_events", "runtime_events", "plan_events",
                        "tool_results", "last_tool_results", "repair_trace"):
                # append-only lists
                if isinstance(value, list):
                    target.setdefault(key, []).extend(value)
                continue
            target[key] = value

    def _session_id(self, req: AgentRunRequest) -> str:
        if req.session_id:
            return str(req.session_id)
        if req.parent_run_id:
            parent = self.db.query(AgentRun).filter(AgentRun.id == req.parent_run_id).first()
            if parent is not None:
                return str(parent.session_id)
        if req.follow_up_context and req.follow_up_context.session_id:
            return str(req.follow_up_context.session_id)
        return str(uuid.uuid4())

    def _build_emitter(self, run_id: str, session_id: str, start_sequence: int) -> EventEmitter:
        def save(event: AgentRuntimeEvent) -> None:
            if self._persist_events:
                self.persistence_sink.record_event(session_id, event)

        return EventEmitter(run_id, save, start_sequence=start_sequence)

    def _observe_events(
        self,
        emit: Any,
        update: dict[str, Any],
        agent_state: Any,
        artifact_identity: AgentArtifactIdentity,
        emitted_ids: set[str],
    ) -> Iterator[AgentRuntimeEvent]:
        artifacts_raw = update.get("artifacts") or []
        for art_dict in artifacts_raw:
            if not isinstance(art_dict, dict):
                continue
            artifact = AgentArtifact.model_validate(art_dict)
            # Sync to agent_state so response builder can pick them up
            if hasattr(agent_state, 'artifacts'):
                agent_state.artifacts.append(artifact)
            if artifact.id not in emitted_ids:
                emitted_ids.add(artifact.id)
                yield emit("agent.artifact.created", artifact=artifact)
                step_name = _artifact_timeline_step(artifact.type)
                if step_name:
                    yield emit(
                        "agent.step.completed",
                        step={
                            "name": step_name,
                            "status": "success",
                            "artifact_id": artifact.id,
                            "artifact_type": artifact.type,
                            "summary": artifact.title,
                        },
                    )

    def _artifacts_from_state(
        self, final_state: dict[str, Any], agent_state: Any
    ) -> list[AgentArtifact]:
        """Build artifacts list from final_state + agent_state merged."""
        seen: set[str] = set()
        result: list[AgentArtifact] = []
        # agent_state reflects SSE emission order (planner + observe); graph state
        # artifacts may arrive in a different append order.
        for source in [
            getattr(agent_state, "artifacts", []) or [],
            final_state.get("artifacts") or [],
        ]:
            for item in source:
                try:
                    art = AgentArtifact.model_validate(item) if isinstance(item, dict) else item
                    if art.id not in seen:
                        seen.add(art.id)
                        result.append(art)
                except Exception:
                    pass
        return result

    def _trace_to_events(
        self, emit: Any, trace: dict[str, Any]
    ) -> Iterator[AgentRuntimeEvent]:
        trace_type = trace.get("type", "")
        tool_name = trace.get("tool_name", "")

        tool_to_step_name = {
            "db.observe": "observe_database",
            "db.search": "search_database",
            "db.inspect": "inspect_database",
            "db.preview": "preview_table",
            "db.query": "query_database",
            "db.remember": "remember_database_semantics",
        }
        mapped_name = tool_to_step_name.get(tool_name, tool_name)

        if trace_type == "agent.tool.started":
            yield emit(
                "agent.step.started",
                step={
                    "name": mapped_name,
                    "tool_name": tool_name,
                    "input": trace.get("input"),
                },
            )
        elif trace_type == "agent.tool.completed":
            yield emit(
                "agent.step.completed",
                step={
                    "name": mapped_name,
                    "tool_name": tool_name,
                    "status": trace.get("status"),
                    "latency_ms": trace.get("latency_ms"),
                    "input": trace.get("input"),
                    "output": trace.get("output"),
                    "error": trace.get("error"),
                },
            )
        elif trace_type == "agent.repair.prepared":
            summary = trace.get("recovery_strategy") or "Preparing SQL repair"
            yield emit(
                "agent.progress.update",
                step={
                    "name": "sql_repair",
                    "status": "running",
                    "summary": summary,
                    "detail": trace.get("error_class"),
                    "attempt": trace.get("attempt"),
                },
            )
        elif trace_type == "agent.repair.attempted":
            summary = trace.get("user_visible_update") or trace.get("recovery_strategy")
            if summary:
                yield emit(
                    "agent.progress.update",
                    step={
                        "name": "sql_repair",
                        "status": "running",
                        "summary": summary,
                        "detail": trace.get("error_class"),
                        "attempt": trace.get("attempt"),
                    },
                )
        elif trace_type == "agent.progress.judged":
            summary = trace.get("user_visible_update") or trace.get("recovery_strategy") or trace.get("reason_summary")
            if summary:
                yield emit(
                    "agent.progress.update",
                    step={
                        "name": trace.get("failure_layer") or "progress",
                        "status": trace.get("status") or "running",
                        "summary": summary,
                        "detail": trace.get("root_cause"),
                        "fastpath": trace.get("fastpath", False),
                    },
                )
        elif trace_type == "agent.model.completed":
            content = _safe_model_progress_text(trace.get("content"))
            tool_names = _tool_call_names(trace.get("tool_calls"))
            if content or tool_names:
                summary = content or f"准备调用工具：{', '.join(tool_names[:3])}"
                yield emit(
                    "agent.progress.update",
                    step={
                        "name": "model",
                        "status": "running" if tool_names else "success",
                        "summary": summary,
                        "tool_calls": tool_names,
                    },
                )
        elif trace_type == "agent.approval.required":
            yield emit("agent.approval.required", step={"name": mapped_name})

    def _approval_events(
        self,
        emit: Any,
        full_state: dict[str, Any],
        agent_state: Any,
        run_id: str,
        session_id: str,
        req: AgentRunRequest,
    ) -> Iterator[AgentRuntimeEvent]:
        pending = full_state.get("pending_approval") or {}
        approval = AgentApprovalRecord.model_validate(pending) if isinstance(pending, dict) else None

        # Build response first (without checkpoint) to get the steps mapped from trace_events
        response = build_response(
            req=req,
            run_id=run_id,
            session_id=session_id,
            state=full_state,
            steps=agent_state.steps,
            artifacts=self._artifacts_from_state(full_state, agent_state),
            success=False,
            error=None,
            status="waiting_approval",
            approval=approval,
            checkpoint=None,
        )

        current_step = response.steps[-1].name if (response.steps and len(response.steps) > 0) else "approval_interrupt"
        next_step = approval.step_name if approval else str(pending.get("tool_name", ""))

        checkpoint = agent_persistence.save_checkpoint(
            self.db,
            run_id=run_id,
            session_id=session_id,
            status="waiting_approval",
            current_step_name=current_step,
            next_step_name=next_step,
            plan=full_state.get("plan"),
            state=dict(full_state),
            completed_steps=[s.model_dump(mode="json") for s in response.steps],
            pending_steps=[
                {
                    "name": pending.get("tool_name", ""),
                    "tool_name": pending.get("tool_name"),
                    "args": (pending.get("requested_action") or {}).get("args", {}),
                }
            ],
        )

        response.checkpoint = checkpoint

        if approval:
            yield emit("agent.approval.required", step={"name": approval.step_name}, approval=approval)
        yield emit("agent.checkpoint.saved", checkpoint=checkpoint)

        try:
            if approval:
                agent_persistence.mark_run_waiting_approval(
                    self.db,
                    run_id=run_id,
                    approval_id=approval.id,
                    current_step_name=approval.step_name,
                )
            self.db.commit()
        except Exception:
            logger.warning("Failed to persist waiting approval state for run %s", run_id)
            self._rollback_quietly()

        yield emit("agent.run.waiting_approval", response=response)

    def _final_events(
        self,
        emit: Any,
        response: AgentRunResponse,
        agent_state: Any,
        emitted_ids: set[str],
    ) -> Iterator[AgentRuntimeEvent]:
        for artifact in response.artifacts:
            if artifact.id not in emitted_ids:
                emitted_ids.add(artifact.id)
                yield emit("agent.artifact.created", artifact=artifact)

        if response.answer:
            yield emit("agent.answer.completed", answer_payload=response.answer)

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
            except Exception:
                logger.warning("Failed to persist final response for run %s", response.run_id)
                self._rollback_quietly()

        return event

    def _start_persistence(self, req: AgentRunRequest, run_id: str, session_id: str) -> None:
        if not self._persist_events:
            return
        try:
            self.persistence_sink.init_run_session(req, run_id, session_id)
        except Exception:
            logger.warning("Failed to start persistence for run %s", run_id)
            self._rollback_quietly()

    def _pending_approval_from_workspace(self, req: AgentRunRequest) -> dict[str, Any] | None:
        workspace = req.workspace_context
        approval_id = getattr(workspace, "pending_approval_id", None) if workspace else None
        if not approval_id:
            return None
        approval = agent_persistence.get_approval(self.db, str(approval_id))
        if approval is None or approval.status != "pending":
            return None
        return approval.model_dump(mode="json")

    def _request_from_run(self, run_id: str) -> AgentRunRequest:
        run = self.db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run is None:
            raise DataBoxError("Agent run not found.", code="RUN_NOT_FOUND")
        return AgentRunRequest(
            datasource_id=str(run.datasource_id),
            question=str(run.question),
            session_id=str(run.session_id),
            parent_run_id=str(run.parent_run_id) if run.parent_run_id else None,
            execute=True,
            max_steps=20,
        )

    def _rollback_quietly(self) -> None:
        try:
            self.db.rollback()
        except Exception:
            pass


    def _context_update_event(
        self,
        emit: Any,
        state: dict[str, Any],
        last_summary: str,
    ) -> tuple[AgentRuntimeEvent | None, str]:
        from engine.agent.context_pack import build_streaming_context_summary

        summary = build_streaming_context_summary(state)
        if not summary or summary == last_summary:
            return None, last_summary
        step_payload: dict[str, Any] = {
            "summary": summary,
            "repair_mode": bool(state.get("repair_mode")),
        }
        visible = state.get("visible_plan") or {}
        if isinstance(visible, dict):
            task_lens = {
                "goal": str(visible.get("goal") or ""),
                "current_focus": str(visible.get("current_focus") or ""),
                "next_likely": str(visible.get("next_likely") or ""),
                "missing_evidence": list(visible.get("missing_evidence") or []),
            }
            if any(task_lens.values()) or task_lens["missing_evidence"]:
                step_payload["task_lens"] = task_lens

        return emit("agent.context.update", step=step_payload), summary


def _artifact_timeline_step(artifact_type: str) -> str | None:
    """Map artifact types to timeline step names for artifact linking."""
    mapping = {
        "table": "query_database",
        "agent_plan": "planner",
    }
    return mapping.get(artifact_type)


def _safe_model_progress_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith(("thought:", "reasoning:", "chain of thought:", "思考:", "推理:")):
        return ""
    if len(text) > 1200:
        return text[:1200].rstrip() + "..."
    return text


def _tool_call_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name = ""
        if isinstance(item, dict):
            name = str(item.get("name") or "")
        else:
            name = str(getattr(item, "name", "") or "")
        if name:
            names.append(name)
    return names
