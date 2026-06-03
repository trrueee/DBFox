from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, Literal, cast

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
from sqlalchemy.orm import Session

from engine.agent import persistence as agent_persistence
from engine.agent.artifact_emitter import ArtifactEmitter
from engine.agent.artifacts import AgentArtifactIdentity
from engine.agent.events import EventEmitter
from engine.agent.state import AgentState
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
from engine.agent_kernel.controller import decide_next_action
from engine.agent_kernel.databinding import apply_tool_result_to_state, merge_state
from engine.agent_kernel.databox_tools import register_databox_tools
from engine.agent_kernel.graph import build_agent_kernel_graph
from engine.agent_kernel.policy import PolicyGate
from engine.agent_kernel.response import AgentKernelResponseAssembler
from engine.agent_kernel.state import KernelState, latest_user_message
from engine.agent_kernel.tool_registry import ToolContext, ToolRegistry

logger = logging.getLogger("databox.agent_kernel.service")


class AgentKernelService:
    _checkpointer = InMemorySaver()

    def __init__(self, db: Session, registry: ToolRegistry | None = None):
        self.db = db
        self.registry = registry or register_databox_tools()
        self.policy_gate = PolicyGate(self.registry)
        self.artifact_emitter = ArtifactEmitter()
        self.response_assembler = AgentKernelResponseAssembler()

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
        return {
            "thread_id": thread_id,
            "values": dict(snapshot.values) if isinstance(snapshot.values, dict) else snapshot.values,
            "next": list(snapshot.next),
            "interrupts": [
                {
                    "id": item.id,
                    "value": item.value,
                }
                for item in snapshot.interrupts
            ],
            "config": snapshot.config,
        }

    def run_iter(self, req: AgentRunRequest) -> Iterator[AgentRuntimeEvent]:
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
            try:
                agent_persistence.record_runtime_event(self.db, session_id, event)
            except Exception:
                logger.warning("Agent kernel persistence: failed to save event %s", event.event_id)
                self._rollback_quietly()

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
                yield from self._events_from_graph_update(
                    emit=emit,
                    node_name=str(node_name),
                    update=update,
                    agent_state=agent_state,
                    artifact_identity=artifact_identity,
                    emitted_artifact_ids=emitted_artifact_ids,
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
        approval = agent_persistence.resolve_approval(
            self.db,
            run_id=run_id,
            approval_id=approval_id,
            decision="approved" if approved else "rejected",
            note=note,
        )
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
            try:
                agent_persistence.record_runtime_event(self.db, session_id, event)
            except Exception:
                logger.warning("Agent kernel persistence: failed to save resume event %s", event.event_id)
                self._rollback_quietly()

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

        for chunk in app.stream(
            Command(resume={"decision": "approved" if approved else "rejected", "note": note}),
            config=config,
            stream_mode="updates",
        ):
            for node_name, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                merge_state(state, update)
                yield from self._events_from_graph_update(
                    emit=emit,
                    node_name=str(node_name),
                    update=update,
                    agent_state=agent_state,
                    artifact_identity=artifact_identity,
                    emitted_artifact_ids=emitted_artifact_ids,
                )

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
            return {
                "status": "failed",
                "error": "Max agent steps reached.",
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

        if decision.action == "call_tool" and decision.tool_call:
            update["pending_tool_call"] = decision.tool_call.model_dump(mode="json")
            return update

        if decision.action == "final_answer":
            update["status"] = "completed"
            if decision.final_answer:
                update["final_answer"] = {
                    "answer": decision.final_answer,
                    "key_findings": [],
                    "evidence": [],
                    "caveats": [],
                    "recommendations": [],
                    "follow_up_questions": [],
                }
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
        update["pending_tool_call"] = None
        update["last_tool_name"] = tool_name
        update["last_observation"] = observation.model_dump(mode="json")
        return update

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

    def _events_from_graph_update(
        self,
        *,
        emit: Any,
        node_name: str,
        update: dict[str, Any],
        agent_state: AgentState,
        artifact_identity: AgentArtifactIdentity,
        emitted_artifact_ids: set[str],
    ) -> Iterator[AgentRuntimeEvent]:
        if node_name == "policy" and isinstance(update.get("pending_approval"), dict):
            approval = AgentApprovalRecord.model_validate(update["pending_approval"])
            yield emit(
                "agent.approval.required",
                step={"name": approval.step_name, "status": "waiting_approval"},
                approval=approval,
            )

        if node_name != "execute_tool" or not isinstance(update.get("last_observation"), dict):
            return

        observation = ToolObservation.model_validate(update["last_observation"])
        tool_name = str(update.get("last_tool_name") or "")
        step_name = observation.name or self._step_name(tool_name)
        yield emit("agent.step.started", step={"name": step_name, "tool_name": tool_name})
        agent_state.apply_observation(step_name, observation)
        yield emit(
            "agent.step.completed",
            step={
                "name": step_name,
                "tool_name": tool_name,
                "status": observation.status,
                "error": observation.error,
                "latency_ms": observation.latency_ms,
            },
        )
        yield from self._artifact_events(emit, observation, agent_state, artifact_identity, emitted_artifact_ids)

    def _approval_from_state(self, state: dict[str, Any]) -> AgentApprovalRecord | None:
        pending = state.get("pending_approval")
        if not isinstance(pending, dict):
            return None
        return AgentApprovalRecord.model_validate(pending)

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
            current_step_name="approval_interrupt",
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

    def _execute_tool(
        self,
        req: AgentRunRequest,
        state: dict[str, Any],
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolObservation:
        tool = self.registry.require(tool_name)
        ctx = ToolContext(db=self.db, request=req, state=dict(state))
        return tool.handler(ctx, args)

    def _artifact_events(
        self,
        emit: Any,
        observation: ToolObservation,
        agent_state: AgentState,
        artifact_identity: AgentArtifactIdentity,
        emitted_artifact_ids: set[str],
    ) -> Iterator[AgentRuntimeEvent]:
        for artifact in self.artifact_emitter.from_observation(observation.name, observation, agent_state, artifact_identity):
            bound = self.artifact_emitter.bind_dependencies(agent_state.artifacts, artifact)
            agent_state.artifacts.append(bound)
            if bound.id in emitted_artifact_ids:
                continue
            emitted_artifact_ids.add(bound.id)
            event = emit("agent.artifact.created", step={"name": observation.name}, artifact=bound)
            yield event
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

        try:
            if response.success:
                agent_persistence.complete_run(self.db, response)
            else:
                agent_persistence.fail_run(self.db, response.run_id, response.session_id, response.error or response.status or "Agent kernel stopped.", response)
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
            status=state.get("status"),
            approval=approval,
            checkpoint=checkpoint,
        )

    def _initial_state(self, req: AgentRunRequest, run_id: str, session_id: str) -> KernelState:
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
            pending_approval=None,
            last_tool_name=None,
            last_observation=None,
            tool_results=[],
            artifacts=[],
            trace_events=[],
            followup_context=None,
            schema_context=None,
            query_plan=None,
            sql_candidate=None,
            sql=None,
            safety=None,
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

    def _start_persistence(self, req: AgentRunRequest, run_id: str, session_id: str) -> None:
        try:
            agent_persistence.create_or_get_session(self.db, req, run_id)
            agent_persistence.start_run(self.db, req, run_id, session_id)
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
            return req.session_id
        if req.follow_up_context and req.follow_up_context.session_id:
            return req.follow_up_context.session_id
        return str(uuid.uuid4())

    def _step_name(self, tool_name: str) -> str:
        return {
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
        }.get(tool_name, tool_name)

    def _rollback_quietly(self) -> None:
        try:
            self.db.rollback()
        except Exception:
            pass


def latest_message_for_debug(state: KernelState) -> str:
    return latest_user_message(state)
