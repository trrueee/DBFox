from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, Literal, cast

from langgraph.types import Command, interrupt
from sqlalchemy.orm import Session

from engine.agent import persistence as agent_persistence
from engine.agent.artifact_emitter import ArtifactEmitter
from engine.agent.artifacts import AgentArtifactIdentity, build_agent_plan_artifact
from engine.agent.events import EventEmitter
from engine.agent.state import AgentState
from engine.agent.tool_runtime_gateway import ToolRuntimeGateway
from engine.agent.types import (
    AgentApprovalRecord,
    AgentAnswer,
    AgentArtifact,
    AgentCheckpointRecord,
    AgentRunRequest,
    AgentRunResponse,
    AgentRuntimeEvent,
    AgentRuntimeEventType,
    AgentStep,
    ToolObservation,
)
from engine.errors import DataBoxError
from engine.models import AgentRun
from engine.agent_kernel.checkpointer import build_agent_kernel_checkpointer
from engine.agent_kernel.controller import decide_next_action
from engine.agent_kernel.databinding import apply_tool_result_to_state, merge_state
from engine.agent_kernel.databox_tools import register_databox_tools
from engine.agent_kernel.event_bridge import events_from_graph_update
from engine.agent_kernel.graph import build_agent_kernel_graph
from engine.agent_kernel.plan_state import apply_plan_patches, plan_patches_for_tool_execution
from engine.agent_kernel.policy import PolicyGate
from engine.agent_kernel.response import AgentKernelResponseAssembler
from engine.agent_kernel.state import KernelState, latest_user_message
from engine.agent_kernel.tool_registry import ToolContext, ToolRegistry

logger = logging.getLogger("databox.agent_kernel.service")


class AgentKernelService:
    # Per-instance checkpointer to prevent state accumulation across farm worker requests
    def __init__(self, db: Session, registry: ToolRegistry | None = None):
        self.db = db
        self.registry = registry or register_databox_tools()
        self.policy_gate = PolicyGate(self.registry)
        self.artifact_emitter = ArtifactEmitter()
        self.response_assembler = AgentKernelResponseAssembler()
        self._checkpointer = build_agent_kernel_checkpointer()
        from engine.agent_kernel.persistence_sink import create_persistence_sink
        self.persistence_sink = create_persistence_sink(db)
        # Combine both env vars: either can disable persistence
        _mode = os.environ.get("AGENT_PERSISTENCE_MODE", "sync")
        _events_flag = os.environ.get("AGENT_PERSIST_RUNTIME_EVENTS", "true")
        self._persist_events = (_mode != "disabled" and _events_flag.lower() != "false")

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        final_response: AgentRunResponse | None = None
        for event in self.run_iter(req):
            if event.response is not None:
                final_response = event.response
        if final_response is None:
            raise RuntimeError("Agent kernel completed without a final response.")
        return final_response

    def resume_approval(
        self,
        *,
        run_id: str,
        approval_id: str,
        approved: bool,
        note: str | None = None,
    ) -> AgentRunResponse:
        final_response: AgentRunResponse | None = None
        for event in self.resume_approval_iter(
            run_id=run_id,
            approval_id=approval_id,
            approved=approved,
            note=note,
        ):
            if event.response is not None:
                final_response = event.response
        if final_response is None:
            raise RuntimeError("Agent kernel resume completed without a final response.")
        return final_response

    def send_message(
        self,
        *,
        datasource_id: str,
        message: str,
        thread_id: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        workspace_context: Any | None = None,
        follow_up_context: Any | None = None,
        execute: bool = True,
        max_steps: int = 20,
    ) -> dict[str, Any]:
        req = AgentRunRequest(
            datasource_id=datasource_id,
            question=message,
            session_id=thread_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            workspace_context=workspace_context,
            follow_up_context=follow_up_context,
            execute=execute,
            max_steps=max_steps,
        )
        response = self.run(req)
        return {
            "thread_id": response.session_id,
            "status": response.status,
            "response": response.model_dump(mode="json"),
        }

    def get_thread_state(self, thread_id: str) -> dict[str, Any]:
        app = build_agent_kernel_graph(
            controller_node=self._controller_node,
            policy_node=self._policy_node,
            execute_tool_node=lambda _graph_state: {},
            approval_interrupt_node=self._approval_interrupt_node,
            checkpointer=self._checkpointer,
        )
        snapshot = app.get_state({"configurable": {"thread_id": thread_id}})
        next_nodes = list(snapshot.next)
        values = dict(snapshot.values) if isinstance(snapshot.values, dict) else snapshot.values
        if not next_nodes:
            fallback = self._thread_state_from_checkpoint(thread_id)
            if fallback is not None:
                return fallback
        return {
            "thread_id": thread_id,
            "values": values,
            "next": next_nodes,
            "interrupts": [
                {
                    "id": item.id,
                    "value": item.value,
                }
                for item in snapshot.interrupts
            ],
            "config": snapshot.config,
        }

    def _thread_state_from_checkpoint(self, thread_id: str) -> dict[str, Any] | None:
        run = (
            self.db.query(AgentRun)
            .filter(AgentRun.session_id == thread_id, AgentRun.status == "waiting_approval")
            .order_by(AgentRun.updated_at.desc())
            .first()
        )
        if run is None:
            return None
        checkpoint_payload = agent_persistence.get_latest_checkpoint_payload(self.db, str(run.id))
        if checkpoint_payload is None:
            return None
        state = checkpoint_payload.get("state")
        record = checkpoint_payload.get("record")
        next_step = getattr(record, "next_step_name", None)
        return {
            "thread_id": thread_id,
            "values": state if isinstance(state, dict) else {},
            "next": ["approval_interrupt"] if next_step else [],
            "interrupts": [
                {
                    "id": f"checkpoint-{getattr(record, 'checkpoint_index', 0)}",
                    "value": {
                        "type": "approval_required",
                        "approval": (state or {}).get("pending_approval") if isinstance(state, dict) else None,
                    },
                }
            ] if next_step else [],
            "config": {"configurable": {"thread_id": thread_id}},
        }

    def run_iter(self, req: AgentRunRequest) -> Iterator[AgentRuntimeEvent]:
        if req.follow_up_context is None and req.parent_run_id:
            reconstructed = agent_persistence.build_followup_context_from_run(self.db, req.parent_run_id)
            if reconstructed is not None:
                req.follow_up_context = reconstructed
                if not req.session_id and reconstructed.session_id:
                    req.session_id = reconstructed.session_id

        run_id = str(uuid.uuid4())
        session_id = self._session_id(req)
        artifact_identity = AgentArtifactIdentity(run_id)
        agent_state = AgentState(
            run_id=run_id,
            session_id=session_id,
            parent_run_id=req.parent_run_id,
            question=req.question,
            datasource_id=req.datasource_id,
        )
        state: dict[str, Any] = dict(self._initial_state(req, run_id, session_id))
        graph_state = dict(state)
        emitted_artifact_ids: set[str] = set()

        def _save_event(event: AgentRuntimeEvent) -> None:
            if not self._persist_events:
                return
            self.persistence_sink.record_event(session_id, event)

        emitter = EventEmitter(run_id, _save_event)

        def emit(
            event_type: AgentRuntimeEventType,
            *,
            step: dict[str, Any] | None = None,
            artifact: AgentArtifact | None = None,
            answer_payload: AgentAnswer | None = None,
            response: AgentRunResponse | None = None,
            approval: AgentApprovalRecord | None = None,
            checkpoint: AgentCheckpointRecord | None = None,
            error: str | None = None,
        ) -> AgentRuntimeEvent:
            return emitter.emit(
                event_type,
                step=step,
                artifact=artifact,
                answer_payload=answer_payload,
                response=response,
                approval=approval,
                checkpoint=checkpoint,
                error=error,
            )

        yield emit(
            "agent.run.started",
            step={"datasource_id": req.datasource_id, "question": req.question, "execute": req.execute},
        )
        self._start_persistence(req, run_id, session_id)

        app = build_agent_kernel_graph(
            controller_node=self._controller_node,
            policy_node=self._policy_node,
            execute_tool_node=lambda graph_state: self._execute_tool_node(req, graph_state),
            approval_interrupt_node=self._approval_interrupt_node,
            checkpointer=self._checkpointer,
        )
        config = {"configurable": {"thread_id": session_id}}

        for chunk in app.stream(graph_state, config=config, stream_mode="updates"):
            for node_name, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                merge_state(state, update)
                if str(node_name) != "execute_tool" and isinstance(update.get("plan"), dict):
                    yield from self._plan_artifact_events(
                        emit,
                        state,
                        agent_state,
                        artifact_identity,
                        emitted_artifact_ids,
                    )
                yield from events_from_graph_update(
                    emit=emit,
                    node_name=str(node_name),
                    update=update,
                    agent_state=agent_state,
                    step_name_for_tool=self._step_name,
                    artifact_events=lambda observation, bridge_agent_state: self._artifact_events(
                        emit,
                        observation,
                        bridge_agent_state,
                        artifact_identity,
                        emitted_artifact_ids,
                    ),
                )
                if str(node_name) == "execute_tool" and isinstance(update.get("plan"), dict):
                    yield from self._plan_artifact_events(
                        emit,
                        state,
                        agent_state,
                        artifact_identity,
                        emitted_artifact_ids,
                    )

        approval = self._approval_from_state(state)
        waiting_approval = state.get("status") == "waiting_approval"
        checkpoint = self._save_waiting_checkpoint(state, agent_state) if waiting_approval else None
        success = state.get("status") == "completed" and not state.get("error")
        response = self._response(
            req,
            state,
            agent_state,
            run_id,
            session_id,
            artifact_identity,
            success=success,
            approval=approval,
            checkpoint=checkpoint,
        )
        yield from self._final_events(
            emit,
            response,
            agent_state,
            emitted_artifact_ids,
            waiting_approval=waiting_approval,
        )

    def resume_approval_iter(
        self,
        *,
        run_id: str,
        approval_id: str,
        approved: bool,
        note: str | None = None,
    ) -> Iterator[AgentRuntimeEvent]:
        existing_approval = agent_persistence.get_approval(self.db, approval_id)
        if existing_approval is None:
            raise DataBoxError("Approval not found.", code="APPROVAL_NOT_FOUND")
        if existing_approval.run_id != run_id:
            raise DataBoxError("Approval does not belong to this run.", code="APPROVAL_RUN_MISMATCH")
        resolved_now = False
        if existing_approval.status == "pending":
            approval = agent_persistence.resolve_approval(
                self.db,
                run_id=run_id,
                approval_id=approval_id,
                decision="approved" if approved else "rejected",
                note=note,
            )
            resolved_now = True
        else:
            approval = existing_approval
            approved = approval.status == "approved"
        req = self._request_from_run(run_id)
        session_id = approval.session_id
        checkpoint_payload = agent_persistence.get_latest_checkpoint_payload(self.db, run_id)
        agent_state = self._agent_state_from_checkpoint(req, run_id, session_id, checkpoint_payload)
        artifact_identity = AgentArtifactIdentity(run_id)
        emitted_artifact_ids = {artifact.id for artifact in agent_state.artifacts}
        state: dict[str, Any] = dict(checkpoint_payload.get("state") or {}) if checkpoint_payload else {}
        if not state:
            state = dict(self._initial_state(req, run_id, session_id))

        def _save_event(event: AgentRuntimeEvent) -> None:
            if not self._persist_events:
                return
            self.persistence_sink.record_event(session_id, event)

        emitter = EventEmitter(
            run_id,
            _save_event,
            start_sequence=agent_persistence.get_latest_runtime_event_sequence(self.db, run_id),
        )

        def emit(
            event_type: AgentRuntimeEventType,
            *,
            step: dict[str, Any] | None = None,
            artifact: AgentArtifact | None = None,
            answer_payload: AgentAnswer | None = None,
            response: AgentRunResponse | None = None,
            approval: AgentApprovalRecord | None = None,
            checkpoint: AgentCheckpointRecord | None = None,
            error: str | None = None,
        ) -> AgentRuntimeEvent:
            return emitter.emit(
                event_type,
                step=step,
                artifact=artifact,
                answer_payload=answer_payload,
                response=response,
                approval=approval,
                checkpoint=checkpoint,
                error=error,
            )

        if resolved_now:
            yield emit(
                "agent.approval.resolved",
                step={"name": approval.step_name, "status": approval.status},
                approval=approval,
            )

        if approved:
            agent_persistence.mark_run_resumed(self.db, run_id=run_id, current_step_name="execute_sql")
            yield emit("agent.run.resumed", step={"name": "execute_sql", "status": "running"}, approval=approval)

        app = build_agent_kernel_graph(
            controller_node=self._controller_node,
            policy_node=self._policy_node,
            execute_tool_node=lambda graph_state: self._execute_tool_node(req, graph_state),
            approval_interrupt_node=self._approval_interrupt_node,
            checkpointer=self._checkpointer,
        )
        config = {"configurable": {"thread_id": session_id}}
        graph_snapshot = app.get_state(config)
        has_graph_checkpoint = bool(graph_snapshot.next) or bool(graph_snapshot.values)

        def stream_graph_updates(chunks: Any) -> Iterator[AgentRuntimeEvent]:
            for chunk in chunks:
                for node_name, update in chunk.items():
                    if not isinstance(update, dict):
                        continue
                    merge_state(state, update)
                    if str(node_name) != "execute_tool" and isinstance(update.get("plan"), dict):
                        yield from self._plan_artifact_events(
                            emit,
                            state,
                            agent_state,
                            artifact_identity,
                            emitted_artifact_ids,
                        )
                    yield from events_from_graph_update(
                        emit=emit,
                        node_name=str(node_name),
                        update=update,
                        agent_state=agent_state,
                        step_name_for_tool=self._step_name,
                        artifact_events=lambda observation, bridge_agent_state: self._artifact_events(
                            emit,
                            observation,
                            bridge_agent_state,
                            artifact_identity,
                            emitted_artifact_ids,
                        ),
                    )
                    if str(node_name) == "execute_tool" and isinstance(update.get("plan"), dict):
                        yield from self._plan_artifact_events(
                            emit,
                            state,
                            agent_state,
                            artifact_identity,
                            emitted_artifact_ids,
                        )

        if has_graph_checkpoint:
            yield from stream_graph_updates(
                app.stream(
                    Command(resume={"decision": "approved" if approved else "rejected", "note": note}),
                    config=config,
                    stream_mode="updates",
                )
            )

        if not approved:
            state["status"] = "failed"
            state["error"] = "User rejected approval."
            state["pending_approval"] = None
            state["pending_tool_call"] = None

        if approved and state.get("status") == "waiting_approval":
            logger.warning(
                "Agent kernel LangGraph checkpoint was unavailable for run %s; resuming from saved DB checkpoint.",
                run_id,
            )
            state.update(self._approved_resume_state_from_saved_checkpoint(state, approval))
            yield from stream_graph_updates(app.stream(dict(state), config=config, stream_mode="updates"))

        final_approval = agent_persistence.get_approval(self.db, approval_id) or approval
        success = state.get("status") == "completed" and not state.get("error")
        response = self._response(
            req,
            state,
            agent_state,
            run_id,
            session_id,
            artifact_identity,
            success=success,
            approval=final_approval,
            checkpoint=checkpoint_payload.get("record") if checkpoint_payload else None,
        )
        yield from self._final_events(emit, response, agent_state, emitted_artifact_ids)

    def _controller_node(self, graph_state: KernelState) -> dict[str, Any]:
        if int(graph_state.get("step_count", 0)) >= int(graph_state.get("max_steps", 20)):
            error = (
                "Agent stopped before SQL validation because max_steps was reached."
                if not graph_state.get("safety")
                else "Max agent steps reached."
            )
            return {
                "status": "failed",
                "error": error,
                "pending_decision": {
                    "action": "final_answer",
                    "final_answer": "Agent stopped before completion because max_steps was reached.",
                },
            }

        decision = decide_next_action(
            state=graph_state,
            available_tools=[spec.model_dump(mode="json") for spec in self.registry.list_specs()],
        )
        update: dict[str, Any] = {
            "pending_decision": decision.model_dump(mode="json"),
            "step_count": int(graph_state.get("step_count", 0)) + 1,
            "trace_events": [{"type": "controller.decision", "payload": decision.model_dump(mode="json")}],
        }

        if decision.plan_patches:
            update["plan_events"] = [patch.model_dump(mode="json") for patch in decision.plan_patches]

        if decision.action == "update_plan":
            update["plan"] = apply_plan_patches(graph_state.get("plan"), decision.plan_patches)
            update["status"] = "running"
            return update

        if decision.action == "call_tool" and decision.tool_call:
            update["pending_tool_call"] = decision.tool_call.model_dump(mode="json")
            return update

        if decision.action == "final_answer":
            update["status"] = "completed"
            if decision.final_answer:
                answer_payload = {
                    "answer": decision.final_answer,
                    "key_findings": [],
                    "evidence": [],
                    "caveats": [],
                    "recommendations": [],
                    "follow_up_questions": [],
                }
                update["final_answer"] = answer_payload
                update["answer"] = answer_payload
            return update

        if decision.action == "ask_user":
            update["status"] = "waiting_user"
            return update

        if decision.action == "wait_approval":
            update["status"] = "waiting_approval"
            return update

        if decision.action == "pause":
            update["status"] = "paused"
            return update

        update["status"] = "failed"
        update["error"] = f"Unsupported controller action: {decision.action}"
        return update

    def _policy_node(self, graph_state: KernelState) -> dict[str, Any]:
        tool_call = graph_state.get("pending_tool_call") or {}
        tool_name = str(tool_call.get("tool_name") or "")
        raw_args = tool_call.get("args")
        args: dict[str, Any] = dict(raw_args) if isinstance(raw_args, dict) else {}
        decision = self.policy_gate.check(dict(graph_state), tool_name, args)

        if decision.status == "blocked":
            return {
                "pending_tool_call": None,
                "error": decision.reason,
                "trace_events": [{"type": "policy.blocked", "payload": decision.model_dump(mode="json")}],
            }

        if decision.status == "approval_required":
            requested_action = {"tool_name": tool_name, "args": decision.safe_args}
            approval = self._approval_record(
                str(graph_state.get("run_id") or ""),
                str(graph_state.get("thread_id") or ""),
                tool_name,
                decision.reason,
                decision.risk_level,
                requested_action,
            )
            return {
                "status": "waiting_approval",
                "pending_tool_call": None,
                "pending_approval": approval.model_dump(mode="json"),
                "trace_events": [{"type": "policy.approval_required", "payload": approval.model_dump(mode="json")}],
            }

        return {
            "pending_tool_call": {"tool_name": tool_name, "args": decision.safe_args},
            "trace_events": [{"type": "policy.allowed", "payload": decision.model_dump(mode="json")}],
        }

    def _execute_tool_node(self, req: AgentRunRequest, graph_state: KernelState) -> dict[str, Any]:
        tool_call = graph_state.get("pending_tool_call") or {}
        tool_name = str(tool_call.get("tool_name") or "")
        raw_args = tool_call.get("args")
        args: dict[str, Any] = dict(raw_args) if isinstance(raw_args, dict) else {}
        observation = self._execute_tool(req, dict(graph_state), tool_name, args)
        update = apply_tool_result_to_state(
            state=dict(graph_state),
            tool_name=tool_name,
            observation=observation,
        )
        self._expire_superseded_approval(dict(graph_state), tool_name, observation)
        plan_patches = plan_patches_for_tool_execution(
            graph_state.get("plan"),
            tool_name=tool_name,
            status=observation.status,
        )
        if plan_patches:
            update["plan_events"] = [patch.model_dump(mode="json") for patch in plan_patches]
            update["plan"] = apply_plan_patches(graph_state.get("plan"), plan_patches)
        update["pending_tool_call"] = None
        update["last_tool_name"] = tool_name
        update["last_observation"] = observation.model_dump(mode="json")
        registered_tool = self.registry.get(tool_name)
        if registered_tool is not None:
            update["last_tool_metadata"] = registered_tool.spec.metadata
        return update

    def _expire_superseded_approval(
        self,
        graph_state: dict[str, Any],
        tool_name: str,
        observation: ToolObservation,
    ) -> None:
        if tool_name != "sql.revise" or observation.status != "success":
            return
        fixed_sql = str((observation.output or {}).get("fixed_sql") or "").strip()
        if not fixed_sql:
            return
        approval = graph_state.get("pending_approval")
        if not isinstance(approval, dict):
            return
        approval_id = str(approval.get("id") or "").strip()
        if not approval_id:
            return
        try:
            agent_persistence.expire_approval(
                self.db,
                approval_id=approval_id,
                note="Superseded by user SQL revision before approval.",
            )
        except Exception:
            logger.warning("Agent kernel persistence: failed to expire superseded approval %s", approval_id)
            self._rollback_quietly()

    def _approval_interrupt_node(self, graph_state: KernelState) -> dict[str, Any]:
        approval = graph_state.get("pending_approval") or {}
        decision = interrupt(
            {
                "type": "approval_required",
                "approval": approval,
                "message": "This action requires approval before the agent can continue.",
            }
        )
        if isinstance(decision, dict) and decision.get("decision") == "approved":
            requested_action = approval.get("requested_action") if isinstance(approval, dict) else {}
            tool_name = str(
                (requested_action or {}).get("tool_name")
                or approval.get("tool_name")
                or ""
            )
            args = (requested_action or {}).get("args") if isinstance(requested_action, dict) else {}
            safety = self._approve_safety(dict(graph_state), approval if isinstance(approval, dict) else {})
            return {
                "status": "running",
                "pending_approval": None,
                "pending_tool_call": {
                    "tool_name": tool_name,
                    "args": dict(args) if isinstance(args, dict) else {},
                },
                "safety": safety,
                "trace_events": [{"type": "approval.approved", "payload": approval}],
            }
        return {
            "status": "failed",
            "pending_approval": None,
            "pending_tool_call": None,
            "error": "User rejected approval.",
            "trace_events": [{"type": "approval.rejected", "payload": approval}],
        }

    def _approval_from_state(self, state: dict[str, Any]) -> AgentApprovalRecord | None:
        pending = state.get("pending_approval")
        if not isinstance(pending, dict):
            return None
        return AgentApprovalRecord.model_validate(pending)

    def _approved_resume_state_from_saved_checkpoint(
        self,
        state: dict[str, Any],
        approval: AgentApprovalRecord,
    ) -> dict[str, Any]:
        approval_payload = approval.model_dump(mode="json")
        safety = self._approve_safety(dict(state), approval_payload)
        return {
            "status": "running",
            "pending_approval": None,
            "pending_tool_call": None,
            "safety": safety,
            "trace_events": [
                {
                    "type": "approval.approved_from_saved_checkpoint",
                    "payload": approval_payload,
                }
            ],
        }

    def _save_waiting_checkpoint(
        self,
        state: dict[str, Any],
        agent_state: AgentState,
    ) -> AgentCheckpointRecord | None:
        approval = self._approval_from_state(state)
        if approval is None:
            return None
        return agent_persistence.save_checkpoint(
            self.db,
            run_id=agent_state.run_id,
            session_id=agent_state.session_id or approval.session_id,
            status="waiting_approval",
            current_step_name=agent_state.steps[-1].name if agent_state.steps else "approval_interrupt",
            next_step_name=self._step_name(approval.tool_name or approval.step_name),
            plan=state.get("plan"),
            state=state,
            completed_steps=[step.model_dump(mode="json") for step in agent_state.steps],
            pending_steps=[
                {
                    "name": self._step_name(approval.tool_name or approval.step_name),
                    "tool_name": approval.tool_name,
                    "args": (approval.requested_action or {}).get("args") if approval.requested_action else {},
                }
            ],
            artifacts=[artifact.model_dump(mode="json") for artifact in agent_state.artifacts],
        )

    def _approve_safety(self, graph_state: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
        raw_safety = graph_state.get("safety")
        safety: dict[str, Any] = dict(raw_safety) if isinstance(raw_safety, dict) else {}
        decision = safety.get("execution_safety_decision")
        execution_decision: dict[str, Any] = dict(decision) if isinstance(decision, dict) else {}
        safe_sql = str(
            execution_decision.get("safe_sql")
            or safety.get("safe_sql")
            or graph_state.get("sql")
            or execution_decision.get("original_sql")
            or ""
        ).strip()
        blocked_reasons = [
            str(reason)
            for reason in (safety.get("blocked_reasons") or [])
            if str(reason) != "requires_confirmation"
        ]
        messages = [str(message) for message in (safety.get("messages") or [])]
        messages.append(f"Agent approval {approval.get('id')} approved execution after manual review.")

        execution_decision["safe_sql"] = safe_sql
        execution_decision["can_execute"] = not blocked_reasons
        execution_decision["passed"] = not blocked_reasons
        execution_decision["requires_confirmation"] = False
        execution_decision["blocked_reasons"] = [
            str(reason)
            for reason in (execution_decision.get("blocked_reasons") or [])
            if str(reason) != "requires_confirmation"
        ]
        execution_decision["messages"] = messages

        safety["safe_sql"] = safe_sql
        safety["can_execute"] = not blocked_reasons
        safety["passed"] = not blocked_reasons
        safety["requires_confirmation"] = False
        safety["blocked_reasons"] = blocked_reasons
        safety["messages"] = messages
        safety["execution_safety_decision"] = execution_decision
        safety["approval"] = {"id": approval.get("id"), "status": "approved"}
        return safety

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

    def _agent_state_from_checkpoint(
        self,
        req: AgentRunRequest,
        run_id: str,
        session_id: str,
        checkpoint_payload: dict[str, Any] | None,
    ) -> AgentState:
        state_payload = checkpoint_payload.get("state") if checkpoint_payload else {}
        state = state_payload if isinstance(state_payload, dict) else {}
        agent_state = AgentState(
            run_id=run_id,
            session_id=session_id,
            parent_run_id=req.parent_run_id,
            question=req.question,
            datasource_id=req.datasource_id,
        )
        completed_steps = checkpoint_payload.get("completed_steps") if checkpoint_payload else []
        if isinstance(completed_steps, list):
            agent_state.steps = [
                AgentStep.model_validate(item)
                for item in completed_steps
                if isinstance(item, dict)
            ]
        artifacts = checkpoint_payload.get("artifacts") if checkpoint_payload else []
        if isinstance(artifacts, list):
            agent_state.artifacts = [
                AgentArtifact.model_validate(item)
                for item in artifacts
                if isinstance(item, dict)
            ]

        self._sync_agent_state_from_graph_state(agent_state, state)
        return agent_state

    def _sync_agent_state_from_graph_state(self, agent_state: AgentState, state: dict[str, Any]) -> None:
        schema_context = state.get("schema_context")
        if isinstance(schema_context, dict):
            agent_state.schema_metadata = schema_context
            agent_state.schema_context = str(schema_context.get("schema_context") or "")
        for attr in (
            "query_plan",
            "sql_candidate",
            "safety",
            "execution",
            "result_profile",
            "chart_suggestion",
            "answer",
        ):
            value = state.get(attr)
            if isinstance(value, dict):
                setattr(agent_state, attr, value)
        followup_context = state.get("followup_context")
        if isinstance(followup_context, dict):
            agent_state.follow_up_context = followup_context
        suggestions = state.get("suggestions")
        if isinstance(suggestions, list):
            agent_state.suggestions = [dict(item) for item in suggestions if isinstance(item, dict)]
        sql = state.get("sql")
        if isinstance(sql, str):
            agent_state.sql = sql

    def _sync_plan_artifact(
        self,
        agent_state: AgentState,
        state: dict[str, Any],
        artifact_identity: AgentArtifactIdentity,
    ) -> None:
        plan = state.get("plan")
        if not isinstance(plan, dict):
            return
        for artifact in self.artifact_emitter.from_plan(plan, artifact_identity):
            bound = self.artifact_emitter.bind_dependencies(agent_state.artifacts, artifact)
            existing_index = next(
                (
                    index
                    for index, existing in enumerate(agent_state.artifacts)
                    if (existing.semantic_id or existing.id) == (bound.semantic_id or bound.id)
                ),
                None,
            )
            if existing_index is None:
                agent_state.artifacts.append(bound)
            else:
                agent_state.artifacts[existing_index] = bound

    def _plan_artifact_events(
        self,
        emit: Any,
        state: dict[str, Any],
        agent_state: AgentState,
        artifact_identity: AgentArtifactIdentity,
        emitted_artifact_ids: set[str],
    ) -> Iterator[AgentRuntimeEvent]:
        plan = state.get("plan")
        if not isinstance(plan, dict):
            return
        for artifact in self.artifact_emitter.from_plan(plan, artifact_identity):
            bound = self.artifact_emitter.bind_dependencies(agent_state.artifacts, artifact)
            existing_index = next(
                (
                    index
                    for index, existing in enumerate(agent_state.artifacts)
                    if (existing.semantic_id or existing.id) == (bound.semantic_id or bound.id)
                ),
                None,
            )
            if existing_index is None:
                agent_state.artifacts.append(bound)
            else:
                agent_state.artifacts[existing_index] = bound
            first_emit = bound.id not in emitted_artifact_ids
            emitted_artifact_ids.add(bound.id)
            yield emit("agent.artifact.created", artifact=bound)
            if not first_emit:
                continue
            try:
                agent_persistence.record_artifact(
                    self.db,
                    agent_state.session_id or "",
                    agent_state.run_id,
                    bound,
                    len(agent_state.artifacts),
                )
            except Exception:
                logger.warning("Agent kernel persistence: failed to save plan artifact %s", bound.id)
                self._rollback_quietly()

    def _execute_tool(
        self,
        req: AgentRunRequest,
        state: dict[str, Any],
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolObservation:
        tool = self.registry.require(tool_name)
        if hasattr(tool, "base_tool") and tool.base_tool is not None:
            from engine.agent.sandbox.base import ExecutionContext
            from engine.agent.types import ToolObservation

            # Prepare state-merged inputs for sandbox BaseTool
            merged_args = dict(args)
            if "question" not in merged_args:
                merged_args["question"] = req.question
            if "schema_context" not in merged_args:
                merged_args["schema_context"] = state.get("schema_context")
            if "query_plan" not in merged_args:
                merged_args["query_plan"] = state.get("query_plan")
            if "follow_up_context" not in merged_args:
                merged_args["follow_up_context"] = state.get("followup_context")
            if "safety" not in merged_args:
                merged_args["safety"] = state.get("safety")
            if "execution" not in merged_args:
                merged_args["execution"] = state.get("execution")
            if "result_profile" not in merged_args:
                merged_args["result_profile"] = state.get("result_profile")
            if "chart_suggestion" not in merged_args:
                merged_args["chart_suggestion"] = state.get("chart_suggestion")
            if "suggestions" not in merged_args:
                merged_args["suggestions"] = state.get("suggestions")
            if "error" not in merged_args:
                merged_args["error"] = state.get("error")
            if "sql" not in merged_args:
                merged_args["sql"] = state.get("sql")

            exec_ctx = ExecutionContext(
                thread_id=str(state.get("thread_id") or state.get("session_id") or ""),
                datasource_id=req.datasource_id,
                db_dialect="mysql",
                read_only=tool.spec.policy.side_effect != "write",
                db_session=self.db,
            )
            start_time = time.perf_counter()
            try:
                base_tool = tool.base_tool
                validated_input = base_tool.input_schema.model_validate(merged_args)
                output_model = base_tool.execute(validated_input, exec_ctx)
                output_dict = output_model.model_dump(mode="json")
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                status = "skipped" if tool_name == "sql.skip_execution" else "success"
                obs_name = self._step_name(tool_name)
                return ToolObservation(
                    name=obs_name,
                    status=status,
                    input=args,
                    output=output_dict,
                    error=None,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                obs_name = self._step_name(tool_name)
                return ToolObservation(
                    name=obs_name,
                    status="failed",
                    input=args,
                    output=None,
                    error=str(exc),
                    latency_ms=latency_ms,
                )

        ctx = ToolContext(db=self.db, request=req, state=dict(state))
        validated_args = ToolRuntimeGateway.validate_input(tool.spec.name, tool.spec.input_model, args)
        observation = tool.handler(ctx, validated_args)
        return ToolRuntimeGateway.validate_observation_output(tool.spec.name, tool.spec.output_model, observation)

    def _artifact_events(
        self,
        emit: Any,
        observation: ToolObservation,
        agent_state: AgentState,
        artifact_identity: AgentArtifactIdentity,
        emitted_artifact_ids: set[str],
    ) -> Iterator[AgentRuntimeEvent]:
        if observation.name.startswith("workspace.") and not any(
            artifact.semantic_id == "agent_plan_draft" for artifact in agent_state.artifacts
        ):
            plan_artifact = self.artifact_emitter.bind_dependencies(
                agent_state.artifacts,
                build_agent_plan_artifact(
                    {
                        "intent": observation.name.removeprefix("workspace."),
                        "tool_name": observation.name,
                        "source": "workspace_context",
                    },
                    identity=artifact_identity,
                ),
            )
            agent_state.artifacts.append(plan_artifact)
            emitted_artifact_ids.add(plan_artifact.id)
            event = emit("agent.artifact.created", step={"name": observation.name}, artifact=plan_artifact)
            yield event
            try:
                agent_persistence.record_artifact(self.db, agent_state.session_id or "", agent_state.run_id, plan_artifact, len(agent_state.artifacts))
            except Exception:
                logger.warning("Agent kernel persistence: failed to save workspace plan artifact %s", plan_artifact.id)
                self._rollback_quietly()

        for artifact in self.artifact_emitter.from_observation(observation.name, observation, agent_state, artifact_identity):
            bound = self.artifact_emitter.bind_dependencies(agent_state.artifacts, artifact)
            agent_state.artifacts.append(bound)
            if bound.id in emitted_artifact_ids:
                continue
            emitted_artifact_ids.add(bound.id)
            event = emit("agent.artifact.created", step={"name": observation.name}, artifact=bound)
            yield event
            if self._persist_events:
                try:
                    agent_persistence.record_artifact(self.db, agent_state.session_id or "", agent_state.run_id, bound, len(agent_state.artifacts))
                except Exception:
                    logger.warning("Agent kernel persistence: failed to save artifact %s", bound.id)
                    self._rollback_quietly()

    def _final_events(
        self,
        emit: Any,
        response: AgentRunResponse,
        agent_state: AgentState,
        emitted_artifact_ids: set[str],
        *,
        waiting_approval: bool = False,
    ) -> Iterator[AgentRuntimeEvent]:
        for artifact in response.artifacts:
            if artifact.id in emitted_artifact_ids:
                continue
            emitted_artifact_ids.add(artifact.id)
            event = emit("agent.artifact.created", artifact=artifact)
            yield event
            if self._persist_events:
                try:
                    agent_persistence.record_artifact(self.db, response.session_id, response.run_id, artifact, len(agent_state.artifacts))
                except Exception:
                    logger.warning("Agent kernel persistence: failed to save final artifact %s", artifact.id)
                    self._rollback_quietly()

        if response.answer is not None:
            event = emit("agent.answer.completed", answer_payload=response.answer)
            yield event

        if waiting_approval:
            if response.checkpoint is not None:
                yield emit("agent.checkpoint.saved", checkpoint=response.checkpoint)
            yield emit("agent.run.waiting_approval", response=response, approval=response.approval)
            try:
                if response.approval is not None:
                    agent_persistence.mark_run_waiting_approval(
                        self.db,
                        run_id=response.run_id,
                        approval_id=response.approval.id,
                        current_step_name=response.approval.step_name,
                        response=response,
                    )
                self.db.commit()
            except Exception:
                logger.warning("Agent kernel persistence: failed to mark run waiting for approval %s", response.run_id)
                self._rollback_quietly()
            return
        else:
            final_type: AgentRuntimeEventType = "agent.run.completed" if response.success else "agent.run.failed"
            yield emit(final_type, response=response, error=response.error)

        if self._persist_events:
            try:
                if response.success:
                    self.persistence_sink.complete_run(response)
                else:
                    self.persistence_sink.fail_run(
                        response.run_id, response.session_id,
                        response.error or response.status or "Agent kernel stopped.", response)
                self.db.commit()
            except Exception:
                logger.warning("Agent kernel persistence: failed to persist final response for run %s", response.run_id)
                self._rollback_quietly()

    def _response(
        self,
        req: AgentRunRequest,
        state: dict[str, Any],
        agent_state: AgentState,
        run_id: str,
        session_id: str,
        artifact_identity: AgentArtifactIdentity,
        *,
        success: bool,
        approval: AgentApprovalRecord | None = None,
        checkpoint: AgentCheckpointRecord | None = None,
    ) -> AgentRunResponse:
        self._sync_agent_state_from_graph_state(agent_state, state)
        self._sync_plan_artifact(agent_state, state, artifact_identity)
        error = state.get("error")
        return self.response_assembler.build_response(
            req=req,
            success=success and not error,
            steps=agent_state.steps,
            query_plan=agent_state.query_plan,
            sql=agent_state.sql,
            safety=agent_state.safety,
            execution=agent_state.execution,
            explanation=str((agent_state.answer or {}).get("answer") or "") or None,
            chart_suggestion=agent_state.chart_suggestion,
            result_profile=agent_state.result_profile,
            answer=agent_state.answer,
            suggestions=agent_state.suggestions,
            error=error,
            run_id=run_id,
            session_id=session_id,
            artifacts=agent_state.artifacts,
            artifact_identity=artifact_identity,
            status=self._response_status(state, error),
            approval=approval,
            checkpoint=checkpoint,
        )

    def _response_status(self, state: dict[str, Any], error: Any) -> str | None:
        if error:
            return "failed"
        return state.get("status")

    def _initial_state(self, req: AgentRunRequest, run_id: str, session_id: str) -> KernelState:
        pending_approval = self._pending_approval_from_workspace(req)
        pending_sql = self._approval_sql(pending_approval)
        pending_safety = self._pending_approval_safety(pending_approval, pending_sql)
        return KernelState(
            thread_id=session_id,
            run_id=run_id,
            datasource_id=req.datasource_id,
            execute=req.execute,
            status="running",
            messages=[{"role": "user", "content": req.question}],
            workspace_context=req.workspace_context,
            follow_up_context=req.follow_up_context,
            goal=req.question,
            plan=None,
            plan_events=[],
            pending_decision=None,
            pending_tool_call=None,
            pending_approval=pending_approval,
            last_tool_name=None,
            last_observation=None,
            tool_results=[],
            artifacts=[],
            trace_events=[],
            followup_context=None,
            schema_context=None,
            query_plan=None,
            sql_candidate=None,
            sql=pending_sql,
            safety=pending_safety,
            execution=None,
            result_profile=None,
            chart_suggestion=None,
            suggestions=[],
            answer=None,
            final_answer=None,
            error=None,
            revision_attempted=False,
            step_count=0,
            max_steps=req.max_steps,
            api_key=req.api_key,
            api_base=req.api_base,
            model_name=req.model_name,
        )

    def _pending_approval_from_workspace(self, req: AgentRunRequest) -> dict[str, Any] | None:
        workspace = req.workspace_context
        approval_id = getattr(workspace, "pending_approval_id", None)
        if not approval_id:
            return None
        approval = agent_persistence.get_approval(self.db, str(approval_id))
        if approval is None or approval.status != "pending":
            return None
        return approval.model_dump(mode="json")

    def _approval_sql(self, approval: dict[str, Any] | None) -> str | None:
        if not isinstance(approval, dict):
            return None
        requested = approval.get("requested_action")
        if not isinstance(requested, dict):
            return None
        args = requested.get("args")
        direct_sql = _string_value(requested.get("safe_sql")) or _string_value(requested.get("sql"))
        if direct_sql:
            return direct_sql
        if isinstance(args, dict):
            return _string_value(args.get("safe_sql")) or _string_value(args.get("sql"))
        return None

    def _pending_approval_safety(
        self,
        approval: dict[str, Any] | None,
        sql: str | None,
    ) -> dict[str, Any] | None:
        if not approval or not sql:
            return None
        messages = []
        if approval.get("reason"):
            messages.append(str(approval["reason"]))
        return {
            "passed": True,
            "can_execute": True,
            "safe_sql": sql,
            "original_sql": sql,
            "requires_confirmation": True,
            "blocked_reasons": ["requires_confirmation"],
            "messages": messages,
            "approval": {"id": approval.get("id"), "status": approval.get("status")},
        }

    def _start_persistence(self, req: AgentRunRequest, run_id: str, session_id: str) -> None:
        if not self._persist_events:
            return
        try:
            self.persistence_sink.init_run_session(req, run_id, session_id)
        except Exception:
            logger.warning("Agent kernel persistence: failed to start run %s", run_id)
            self._rollback_quietly()

    def _approval_record(
        self,
        run_id: str,
        session_id: str,
        tool_name: str,
        reason: str,
        risk_level: str,
        requested_action: dict[str, Any],
    ) -> AgentApprovalRecord:
        normalized_risk: Literal["safe", "warning", "danger"] = (
            cast(Literal["safe", "warning", "danger"], risk_level)
            if risk_level in {"safe", "warning", "danger"}
            else "warning"
        )
        return agent_persistence.create_approval(
            self.db,
            run_id=run_id,
            session_id=session_id,
            step_name=self._step_name(tool_name),
            tool_name=tool_name,
            risk_level=normalized_risk,
            reason=reason,
            policy_decision={"reason": reason, "risk_level": risk_level, "requested_action": requested_action},
            requested_action=requested_action,
        )

    def _session_id(self, req: AgentRunRequest) -> str:
        if req.session_id:
            return str(req.session_id)
        if req.follow_up_context and req.follow_up_context.session_id:
            return str(req.follow_up_context.session_id)
        return str(uuid.uuid4())

    def _step_name(self, tool_name: str) -> str:
        step_names = {
            "followup.load_context": "load_follow_up_context",
            "schema.build_context": "build_schema_context",
            "query_plan.build": "build_query_plan",
            "sql.generate": "generate_sql_candidate",
            "sql.validate": "validate_sql",
            "sql.execute_readonly": "execute_sql",
            "sql.skip_execution": "execute_sql",
            "sql.revise": "revise_sql",
            "result.profile": "profile_result",
            "chart.suggest": "suggest_chart",
            "followup.suggest": "suggest_followups",
            "answer.synthesize": "answer_synthesizer",
        }
        return step_names.get(tool_name, tool_name)

    def _rollback_quietly(self) -> None:
        try:
            self.db.rollback()
        except Exception:
            pass


def latest_message_for_debug(state: KernelState) -> str:
    return str(latest_user_message(state))


def _string_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


