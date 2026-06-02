from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from engine.agent import persistence as agent_persistence
from engine.agent.answer import synthesize_agent_answer
from engine.agent.artifact_emitter import ArtifactEmitter
from engine.agent.artifacts import (
    AgentArtifactIdentity,
    build_agent_plan_artifact,
    build_agent_artifacts,
    build_error_artifact,
    build_recommendations_artifact,
)
from engine.agent.context import build_response_context_summary, has_follow_up_context, referenced_artifact_ids
from engine.agent.default_tools import build_default_tool_registry
from engine.agent.events import EventEmitter, build_trace_events
from engine.agent.executor import AgentStepSpec, StepExecutor
from engine.agent.narration import build_message_blocks, build_visible_events
from engine.agent.plan_validator import AgentPlanValidator
from engine.agent.planner import AgentPlanner, WORKSPACE_TOOL_BY_INTENT
from engine.agent.registry import AgentToolContext, ToolRegistry
from engine.agent.state import AgentState
from engine.agent.validation import validate_agent_response_contract
from engine.agent.tools import skipped_execute_observation
from engine.agent.types import (
    AgentAnswer,
    AgentApprovalRecord,
    AgentArtifact,
    AgentCheckpointRecord,
    AgentPlanDraft,
    AgentRunRequest,
    AgentRunResponse,
    AgentRuntimeEvent,
    AgentRuntimeEventType,
    AgentStep,
    FollowUpSuggestion,
    ResultProfile,
    ToolObservation,
)
from engine.agent.workspace_context import build_agent_context_bundle
from engine.errors import DataBoxError
from engine.models import AgentRun

logger = logging.getLogger("databox.agent.runtime")

APPROVAL_HARD_BLOCKERS = {"guardrail_reject", "schema_validation", "datasource_scope", "select_star"}


class DataBoxAgentRuntime:
    def __init__(self, db: Session, registry: ToolRegistry | None = None):
        self.db = db
        self.registry = registry or build_default_tool_registry()
        self.step_executor = StepExecutor(self.registry)
        self.artifact_emitter = ArtifactEmitter()
        self.planner = AgentPlanner(self.registry)
        self.plan_validator = AgentPlanValidator(self.registry)

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        final_response: AgentRunResponse | None = None
        for event in self.run_iter(req):
            if event.response is not None:
                final_response = event.response
        if final_response is None:
            raise RuntimeError("Agent runtime completed without a final response.")
        return final_response

    def build_default_plan(self, request: AgentRunRequest) -> list[AgentStepSpec]:
        steps: list[AgentStepSpec] = []
        if has_follow_up_context(request) or request.parent_run_id:
            steps.append(AgentStepSpec(name="load_follow_up_context", tool_name="followup.load_context"))
        steps.extend(
            [
                AgentStepSpec(name="build_schema_context", tool_name="schema.build_context"),
                AgentStepSpec(name="build_query_plan", tool_name="query_plan.build"),
                AgentStepSpec(name="generate_sql_candidate", tool_name="sql.generate_candidate"),
                AgentStepSpec(name="validate_sql", tool_name="sql.validate"),
                AgentStepSpec(name="execute_sql", tool_name="sql.execute_readonly", required=request.execute),
                AgentStepSpec(name="profile_result", tool_name="result.profile", required=False),
                AgentStepSpec(name="suggest_chart", tool_name="chart.suggest", required=False),
                AgentStepSpec(name="suggest_followups", tool_name="followup.suggest", required=False),
                AgentStepSpec(name="answer_synthesizer", tool_name="answer.synthesize"),
            ]
        )
        return steps

    def run_iter(self, req: AgentRunRequest) -> Iterator[AgentRuntimeEvent]:
        run_id = str(uuid.uuid4())
        session_id = self._session_id(req)

        if not has_follow_up_context(req) and req.parent_run_id:
            reconstructed = agent_persistence.build_followup_context_from_run(self.db, req.parent_run_id)
            if reconstructed is not None:
                req.follow_up_context = reconstructed
                if not req.session_id:
                    req.session_id = reconstructed.session_id
                    if reconstructed.session_id:
                        session_id = reconstructed.session_id
        artifact_identity = AgentArtifactIdentity(run_id)
        state = AgentState(
            run_id=run_id,
            session_id=session_id,
            parent_run_id=req.parent_run_id,
            question=req.question,
            datasource_id=req.datasource_id,
        )
        steps = state.steps
        artifacts = state.artifacts
        emitted_artifact_ids: set[str] = set()
        explanation: str | None = None

        def _save_event(event: AgentRuntimeEvent) -> None:
            try:
                agent_persistence.record_runtime_event(self.db, session_id, event)
            except Exception:
                logger.warning("Persistence: failed to save event %s", event.event_id)
                try:
                    self.db.rollback()
                except Exception:
                    pass

        event_emitter = EventEmitter(run_id, _save_event)
        tool_ctx = AgentToolContext(db=self.db, request=req, state=state)

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
            return event_emitter.emit(
                event_type,
                step=step,
                artifact=artifact,
                answer_payload=answer_payload,
                response=response,
                approval=approval,
                checkpoint=checkpoint,
                error=error,
            )

        def _save_artifact_record(artifact: AgentArtifact, seq: int) -> None:
            try:
                agent_persistence.record_artifact(self.db, session_id, run_id, artifact, seq)
            except Exception:
                logger.warning("Persistence: failed to save artifact %s", artifact.id)
                try:
                    self.db.rollback()
                except Exception:
                    pass

        def start_step(name: str) -> AgentRuntimeEvent:
            return emit(
                "agent.step.started",
                step={"name": name, "index": len(steps) + 1},
            )

        def execute_step(
            name: str,
            tool_name: str,
            input_override: dict[str, Any] | None = None,
        ) -> tuple[AgentStep, ToolObservation]:
            step, observation = self.step_executor.execute_step(
                AgentStepSpec(name=name, tool_name=tool_name),
                state,
                tool_ctx,
                input_override=input_override,
            )
            state.apply_observation(name, observation, agent_step=step)
            return step, observation

        def complete_step(step: AgentStep) -> AgentRuntimeEvent:
            return emit(
                "agent.step.completed",
                step={
                    "name": step.name,
                    "status": step.status,
                    "error": step.error,
                    "latency_ms": step.latency_ms,
                    "index": len(steps),
                },
            )

        def final_events(response: AgentRunResponse) -> Iterator[AgentRuntimeEvent]:
            for artifact in response.artifacts:
                if artifact.id in emitted_artifact_ids:
                    continue
                emitted_artifact_ids.add(artifact.id)
                event = emit("agent.artifact.created", artifact=artifact)
                yield event
                _save_artifact_record(artifact, len(artifacts))
            if response.answer is not None:
                yield emit("agent.answer.completed", answer_payload=response.answer)
            final_type: AgentRuntimeEventType = "agent.run.completed" if response.success else "agent.run.failed"
            yield emit(final_type, response=response, error=response.error)
            try:
                if response.success:
                    agent_persistence.complete_run(self.db, response)
                else:
                    agent_persistence.fail_run(self.db, run_id, session_id, response.error or "Agent run failed.", response)
                self.db.commit()
            except Exception:
                logger.warning("Persistence: failed to persist final response for run %s", run_id)
                try:
                    self.db.rollback()
                except Exception:
                    pass

        def append_artifact(artifact: AgentArtifact) -> AgentRuntimeEvent:
            bound_artifact = self.artifact_emitter.bind_dependencies(artifacts, artifact)
            artifacts.append(bound_artifact)
            emitted_artifact_ids.add(bound_artifact.id)
            event = emit("agent.artifact.created", artifact=bound_artifact)
            _save_artifact_record(bound_artifact, len(artifacts))
            return event

        def append_artifacts_from_observation(
            name: str,
            observation: ToolObservation,
        ) -> Iterator[AgentRuntimeEvent]:
            for artifact in self.artifact_emitter.from_observation(name, observation, state, artifact_identity):
                yield append_artifact(artifact)

        def build_failure(error: str, plan: dict[str, Any] | None = None) -> AgentRunResponse:
            return self._failure(
                req,
                steps,
                error,
                query_plan=plan,
                run_id=run_id,
                session_id=session_id,
                artifacts=artifacts,
                artifact_identity=artifact_identity,
            )

        yield emit(
            "agent.run.started",
            step={
                "datasource_id": req.datasource_id,
                "question": req.question,
                "execute": req.execute,
            },
        )

        try:
            agent_persistence.create_or_get_session(self.db, req, run_id)
        except Exception:
            logger.warning("Persistence: failed to create session for run %s", run_id)
            try:
                self.db.rollback()
            except Exception:
                pass
        try:
            agent_persistence.start_run(self.db, req, run_id, session_id)
        except Exception:
            logger.warning("Persistence: failed to start run %s", run_id)
            try:
                self.db.rollback()
            except Exception:
                pass

        context_bundle = build_agent_context_bundle(self.db, req)
        plan_draft = self.planner.plan(self.db, req, context_bundle)
        validation = self.plan_validator.validate(req, plan_draft, context_bundle)
        yield append_artifact(
            build_agent_plan_artifact(
                {
                    **plan_draft.model_dump(mode="json"),
                    "validation": validation.model_dump(mode="json", exclude={"normalized_plan"}),
                },
                identity=artifact_identity,
            )
        )
        if not validation.valid:
            response = self._response(
                req=req,
                success=False,
                steps=steps,
                query_plan=None,
                sql=None,
                safety=None,
                execution=None,
                explanation=None,
                chart_suggestion=None,
                result_profile=None,
                answer=None,
                suggestions=[],
                error=f"Agent plan rejected: {'; '.join(validation.reasons)}",
                run_id=run_id,
                session_id=session_id,
                artifacts=artifacts,
                artifact_identity=artifact_identity,
            )
            yield from final_events(response)
            return

        workspace_tool_name = self._workspace_tool_name(plan_draft)
        if workspace_tool_name:
            yield start_step(workspace_tool_name)
            workspace_step, workspace_obs = execute_step(
                workspace_tool_name,
                workspace_tool_name,
                {"intent": plan_draft.intent.intent, "context_bundle": context_bundle},
            )
            yield complete_step(workspace_step)
            yield from append_artifacts_from_observation(workspace_tool_name, workspace_obs)
            if workspace_obs.status == "failed":
                yield from final_events(build_failure(workspace_obs.error or "Workspace assistance failed."))
                return
            workspace_output = workspace_obs.output or {}
            answer_payload = self._workspace_answer_payload(workspace_output)
            state.answer = answer_payload
            explanation = str(workspace_output.get("answer") or "")
            response = self._response(
                req=req,
                success=True,
                steps=steps,
                query_plan=None,
                sql=str(workspace_output.get("proposed_sql") or "") or None,
                safety=None,
                execution=None,
                explanation=explanation,
                chart_suggestion=None,
                result_profile=None,
                answer=answer_payload,
                suggestions=[],
                error=None,
                run_id=run_id,
                session_id=session_id,
                artifacts=artifacts,
                artifact_identity=artifact_identity,
            )
            yield from final_events(response)
            return

        if has_follow_up_context(req):
            yield start_step("load_follow_up_context")
            context_step, context_obs = execute_step("load_follow_up_context", "followup.load_context")
            yield complete_step(context_step)
            if context_obs.status == "failed":
                yield from final_events(build_failure("Failed to load follow-up context."))
                return
            if self._budget_reached(req, steps):
                yield from final_events(build_failure("Agent stopped before schema linking because max_steps was reached."))
                return

        yield start_step("build_schema_context")
        schema_step, schema_obs = execute_step("build_schema_context", "schema.build_context")
        yield complete_step(schema_step)
        if schema_obs.status == "failed":
            yield from final_events(build_failure("Failed to build schema context."))
            return

        if self._budget_reached(req, steps):
            yield from final_events(build_failure("Agent stopped before query planning because max_steps was reached."))
            return

        yield start_step("build_query_plan")
        plan_step, plan_obs = execute_step("build_query_plan", "query_plan.build")
        yield complete_step(plan_step)
        if plan_obs.status == "failed":
            yield from final_events(build_failure("Failed to build query plan."))
            return
        yield from append_artifacts_from_observation("build_query_plan", plan_obs)

        if self._budget_reached(req, steps):
            yield from final_events(build_failure("Agent stopped before SQL generation because max_steps was reached.", state.query_plan))
            return

        yield start_step("generate_sql_candidate")
        sql_step, sql_obs = execute_step("generate_sql_candidate", "sql.generate_candidate")
        yield complete_step(sql_step)
        if sql_obs.status == "failed":
            yield start_step("revise_sql")
            revise_step, revise_obs = execute_step(
                "revise_sql",
                "sql.revise",
                {"sql": None, "error": sql_obs.error or "SQL generation failed."},
            )
            yield complete_step(revise_step)
            yield from final_events(build_failure(sql_obs.error or "Failed to generate SQL.", state.query_plan))
            return

        sql_output = sql_obs.output or {}
        sql = state.sql or str(sql_output.get("sql") or "").strip()
        if not sql:
            yield start_step("revise_sql")
            revise_step, revise_obs = execute_step(
                "revise_sql",
                "sql.revise",
                {"sql": sql, "error": "SQL generation returned an empty candidate."},
            )
            yield complete_step(revise_step)
            yield from final_events(build_failure("SQL generation returned an empty candidate.", state.query_plan))
            return

        if self._budget_reached(req, steps):
            yield from final_events(build_failure("Agent stopped before SQL validation because max_steps was reached.", state.query_plan))
            return

        yield start_step("validate_sql")
        validate_step, validate_obs = execute_step("validate_sql", "sql.validate", {"sql": sql})
        yield complete_step(validate_step)
        safety = state.safety or validate_obs.output or {}
        self._attach_generation_notes(safety, sql_output)
        state.safety = safety
        state.sql = sql
        yield from append_artifacts_from_observation("validate_sql", validate_obs)
        if validate_obs.status != "failed" and self._should_wait_for_approval(safety):
            approval = agent_persistence.create_approval(
                self.db,
                run_id=run_id,
                session_id=session_id,
                step_name="validate_sql",
                tool_name="sql.execute_readonly",
                risk_level=self._approval_risk_level(safety),
                reason=self._approval_reason(safety),
                policy_decision=self._policy_decision(safety),
                requested_action=self._requested_action(req, state, sql),
            )
            checkpoint = agent_persistence.save_checkpoint(
                self.db,
                run_id=run_id,
                session_id=session_id,
                status="waiting_approval",
                current_step_name="validate_sql",
                next_step_name="execute_sql",
                plan=[step.model_dump(mode="json") for step in self.build_default_plan(req)],
                state=state.model_dump(mode="json"),
                completed_steps=[step.model_dump(mode="json") for step in state.steps],
                pending_steps=self._pending_step_specs(req, after_step="validate_sql"),
                artifacts=[artifact.model_dump(mode="json") for artifact in artifacts],
            )
            response = self._response(
                req=req,
                success=False,
                steps=steps,
                query_plan=state.query_plan,
                sql=state.sql or sql,
                safety=safety,
                execution=None,
                explanation=None,
                chart_suggestion=None,
                result_profile=None,
                answer=None,
                suggestions=[],
                error=None,
                run_id=run_id,
                session_id=session_id,
                artifacts=artifacts,
                artifact_identity=artifact_identity,
                status="waiting_approval",
                approval=approval,
                checkpoint=checkpoint,
            )
            agent_persistence.mark_run_waiting_approval(
                self.db,
                run_id=run_id,
                approval_id=approval.id,
                current_step_name="validate_sql",
                response=response,
            )
            approval_event = emit(
                "agent.approval.required",
                step={"name": "validate_sql", "next_step": "execute_sql"},
                approval=approval,
            )
            checkpoint_event = emit(
                "agent.checkpoint.saved",
                step={"name": "validate_sql", "next_step": "execute_sql"},
                checkpoint=checkpoint,
            )
            waiting_event = emit(
                "agent.run.waiting_approval",
                step={"name": "execute_sql", "status": "waiting_approval"},
                response=response,
                approval=approval,
                checkpoint=checkpoint,
            )
            self.db.commit()
            yield approval_event
            yield checkpoint_event
            yield waiting_event
            return
        if validate_obs.status == "failed" or not safety.get("can_execute"):
            reason = (
                safety.get("revise_suggestion")
                or validate_obs.error
                or "SQL did not pass DataBox Agent validation."
            )
            yield start_step("revise_sql")
            revise_step, revise_obs = execute_step(
                "revise_sql",
                "sql.revise",
                {"sql": sql, "error": str(reason), "safety": safety},
            )
            yield complete_step(revise_step)
            response = self._response(
                req=req,
                success=False,
                steps=steps,
                query_plan=state.query_plan,
                sql=sql,
                safety=safety,
                execution=None,
                explanation=None,
                chart_suggestion=None,
                result_profile=None,
                answer=None,
                suggestions=[],
                error=str(reason),
                run_id=run_id,
                session_id=session_id,
                artifacts=artifacts,
                artifact_identity=artifact_identity,
            )
            yield from final_events(response)
            return

        safe_sql = str(safety.get("safe_sql") or sql)
        sql = safe_sql
        state.sql = safe_sql

        if req.execute:
            if self._budget_reached(req, steps):
                response = self._response(
                    req=req,
                    success=False,
                    steps=steps,
                    query_plan=state.query_plan,
                    sql=safe_sql,
                    safety=safety,
                    execution=None,
                    explanation=None,
                    chart_suggestion=None,
                    result_profile=None,
                    answer=None,
                    suggestions=[],
                    error="Agent stopped before SQL execution because max_steps was reached.",
                    run_id=run_id,
                    session_id=session_id,
                    artifacts=artifacts,
                    artifact_identity=artifact_identity,
                )
                yield from final_events(response)
                return

            yield start_step("execute_sql")
            execute_step_result, execute_obs = execute_step(
                "execute_sql",
                "sql.execute_readonly",
                {"sql": safe_sql, "safety": safety},
            )
            yield complete_step(execute_step_result)
            execution = state.execution or execute_obs.output or {}
            yield from append_artifacts_from_observation("execute_sql", execute_obs)
            if execute_obs.status == "failed":
                reason = (
                    execution.get("revise_suggestion")
                    or execute_obs.error
                    or "SQL execution failed."
                )
                yield start_step("revise_sql")
                revise_step, revise_obs = execute_step(
                    "revise_sql",
                    "sql.revise",
                    {"sql": safe_sql, "error": str(reason), "safety": safety},
                )
                yield complete_step(revise_step)
                response = self._response(
                    req=req,
                    success=False,
                    steps=steps,
                    query_plan=state.query_plan,
                    sql=safe_sql,
                    safety=safety,
                    execution=execution,
                    explanation=None,
                    chart_suggestion=None,
                    result_profile=None,
                    answer=None,
                    suggestions=[],
                    error=str(reason),
                    run_id=run_id,
                    session_id=session_id,
                    artifacts=artifacts,
                    artifact_identity=artifact_identity,
                )
                yield from final_events(response)
                return
        else:
            yield start_step("execute_sql")
            execute_obs = skipped_execute_observation()
            state.apply_observation("execute_sql", execute_obs)
            yield complete_step(steps[-1])

        if not self._budget_reached(req, steps):
            yield start_step("profile_result")
            profile_step, profile_obs = execute_step("profile_result", "result.profile")
            yield complete_step(profile_step)
            yield from append_artifacts_from_observation("profile_result", profile_obs)

        if not self._budget_reached(req, steps):
            yield start_step("suggest_chart")
            chart_step, chart_obs = execute_step("suggest_chart", "chart.suggest")
            yield complete_step(chart_step)
            yield from append_artifacts_from_observation("suggest_chart", chart_obs)

        if not self._budget_reached(req, steps):
            yield start_step("suggest_followups")
            suggestions_step, suggestions_obs = execute_step("suggest_followups", "followup.suggest")
            yield complete_step(suggestions_step)

        if not self._budget_reached(req, steps):
            yield start_step("answer_synthesizer")
            answer_step, answer_obs = execute_step("answer_synthesizer", "answer.synthesize")
            yield complete_step(answer_step)
            if state.answer:
                explanation = str(state.answer.get("answer") or "")

        response = self._response(
            req=req,
            success=True,
            steps=steps,
            query_plan=state.query_plan,
            sql=safe_sql,
            safety=safety,
            execution=state.execution,
            explanation=explanation,
            chart_suggestion=state.chart_suggestion,
            result_profile=state.result_profile,
            answer=state.answer,
            suggestions=state.suggestions,
            error=None,
            run_id=run_id,
            session_id=session_id,
            artifacts=artifacts,
            artifact_identity=artifact_identity,
        )
        yield from final_events(response)

    def resume(self, run_id: str, approval_id: str | None = None) -> AgentRunResponse:
        final_response: AgentRunResponse | None = None
        for event in self.resume_iter(run_id, approval_id):
            if event.response is not None:
                final_response = event.response
        if final_response is None:
            raise RuntimeError("Agent runtime resume completed without a final response.")
        return final_response

    def resume_iter(self, run_id: str, approval_id: str | None = None) -> Iterator[AgentRuntimeEvent]:
        run = self.db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run is None:
            raise DataBoxError(f"Agent run {run_id} not found.", code="RUN_NOT_FOUND")
        if run.status != "waiting_approval":
            raise DataBoxError("Agent run is not waiting for approval.", code="RUN_NOT_WAITING_APPROVAL")

        checkpoint_payload = agent_persistence.get_latest_checkpoint_payload(self.db, run_id)
        if checkpoint_payload is None:
            raise DataBoxError("No checkpoint is available for this run.", code="CHECKPOINT_NOT_FOUND")

        checkpoint = checkpoint_payload["record"]
        if checkpoint.next_step_name != "execute_sql":
            raise DataBoxError("Only resume from execute_sql is supported in this version.", code="UNSUPPORTED_RESUME_POINT")

        resolved_approval_id = approval_id or str(run.waiting_approval_id or "")
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
        if approval.status == "rejected":
            agent_persistence.fail_run(self.db, run_id, run.session_id, "Approval rejected")
            self.db.commit()
            raise DataBoxError("Approval rejected.", code="APPROVAL_REJECTED")
        if approval.status != "approved":
            raise DataBoxError(f"Approval status {approval.status} cannot resume this run.", code="APPROVAL_NOT_APPROVED")

        state_payload = checkpoint_payload.get("state")
        if not isinstance(state_payload, dict):
            raise DataBoxError("Checkpoint state is not restorable.", code="CHECKPOINT_INVALID")
        state = AgentState.model_validate(state_payload)
        state.run_id = run_id
        state.session_id = run.session_id
        state.datasource_id = run.datasource_id
        state.question = run.question

        req = AgentRunRequest(
            datasource_id=run.datasource_id,
            question=run.question,
            session_id=run.session_id,
            parent_run_id=run.parent_run_id,
            execute=True,
        )
        safe_sql = self._approve_safety_for_execution(state, approval)
        safety = state.safety or {}
        steps = state.steps
        artifacts = state.artifacts
        emitted_artifact_ids = {artifact.id for artifact in artifacts}
        artifact_identity = AgentArtifactIdentity(run_id)
        explanation: str | None = None

        def _save_event(event: AgentRuntimeEvent) -> None:
            try:
                agent_persistence.record_runtime_event(self.db, run.session_id, event)
            except Exception:
                logger.warning("Persistence: failed to save resume event %s", event.event_id)
                try:
                    self.db.rollback()
                except Exception:
                    pass

        event_emitter = EventEmitter(
            run_id,
            _save_event,
            start_sequence=agent_persistence.get_latest_runtime_event_sequence(self.db, run_id),
        )
        tool_ctx = AgentToolContext(db=self.db, request=req, state=state)

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
            return event_emitter.emit(
                event_type,
                step=step,
                artifact=artifact,
                answer_payload=answer_payload,
                response=response,
                approval=approval,
                checkpoint=checkpoint,
                error=error,
            )

        def _save_artifact_record(artifact: AgentArtifact, seq: int) -> None:
            try:
                agent_persistence.record_artifact(self.db, run.session_id, run_id, artifact, seq)
            except Exception:
                logger.warning("Persistence: failed to save resume artifact %s", artifact.id)
                try:
                    self.db.rollback()
                except Exception:
                    pass

        def start_step(name: str) -> AgentRuntimeEvent:
            return emit("agent.step.started", step={"name": name, "index": len(steps) + 1})

        def execute_step(
            name: str,
            tool_name: str,
            input_override: dict[str, Any] | None = None,
        ) -> tuple[AgentStep, ToolObservation]:
            step, observation = self.step_executor.execute_step(
                AgentStepSpec(name=name, tool_name=tool_name),
                state,
                tool_ctx,
                input_override=input_override,
            )
            state.apply_observation(name, observation, agent_step=step)
            return step, observation

        def complete_step(step: AgentStep) -> AgentRuntimeEvent:
            return emit(
                "agent.step.completed",
                step={
                    "name": step.name,
                    "status": step.status,
                    "error": step.error,
                    "latency_ms": step.latency_ms,
                    "index": len(steps),
                },
            )

        def append_artifact(artifact: AgentArtifact) -> AgentRuntimeEvent:
            bound_artifact = self.artifact_emitter.bind_dependencies(artifacts, artifact)
            artifacts.append(bound_artifact)
            emitted_artifact_ids.add(bound_artifact.id)
            event = emit("agent.artifact.created", artifact=bound_artifact)
            _save_artifact_record(bound_artifact, len(artifacts))
            return event

        def append_artifacts_from_observation(
            name: str,
            observation: ToolObservation,
        ) -> Iterator[AgentRuntimeEvent]:
            for artifact in self.artifact_emitter.from_observation(name, observation, state, artifact_identity):
                yield append_artifact(artifact)

        def final_events(response: AgentRunResponse) -> Iterator[AgentRuntimeEvent]:
            for artifact in response.artifacts:
                if artifact.id in emitted_artifact_ids:
                    continue
                emitted_artifact_ids.add(artifact.id)
                event = emit("agent.artifact.created", artifact=artifact)
                yield event
                _save_artifact_record(artifact, len(artifacts))
            if response.answer is not None:
                yield emit("agent.answer.completed", answer_payload=response.answer)
            final_type: AgentRuntimeEventType = "agent.run.completed" if response.success else "agent.run.failed"
            yield emit(final_type, response=response, error=response.error)
            try:
                if response.success:
                    agent_persistence.complete_run(self.db, response)
                else:
                    agent_persistence.fail_run(self.db, run_id, run.session_id, response.error or "Agent run failed.", response)
                self.db.commit()
            except Exception:
                logger.warning("Persistence: failed to persist resumed response for run %s", run_id)
                try:
                    self.db.rollback()
                except Exception:
                    pass

        agent_persistence.mark_run_resumed(self.db, run_id=run_id, current_step_name="execute_sql")
        resumed_event = emit(
            "agent.run.resumed",
            step={"name": "execute_sql", "status": "running"},
            approval=approval,
            checkpoint=checkpoint,
        )
        self.db.commit()
        yield resumed_event

        yield start_step("execute_sql")
        execute_step_result, execute_obs = execute_step(
            "execute_sql",
            "sql.execute_readonly",
            {"sql": safe_sql, "safety": safety},
        )
        yield complete_step(execute_step_result)
        execution = state.execution or execute_obs.output or {}
        yield from append_artifacts_from_observation("execute_sql", execute_obs)
        if execute_obs.status == "failed":
            reason = (
                execution.get("revise_suggestion")
                or execute_obs.error
                or "SQL execution failed."
            )
            yield start_step("revise_sql")
            revise_step, revise_obs = execute_step(
                "revise_sql",
                "sql.revise",
                {"sql": safe_sql, "error": str(reason), "safety": safety},
            )
            yield complete_step(revise_step)
            response = self._response(
                req=req,
                success=False,
                steps=steps,
                query_plan=state.query_plan,
                sql=safe_sql,
                safety=safety,
                execution=execution,
                explanation=None,
                chart_suggestion=None,
                result_profile=None,
                answer=None,
                suggestions=[],
                error=str(reason),
                run_id=run_id,
                session_id=run.session_id,
                artifacts=artifacts,
                artifact_identity=artifact_identity,
            )
            yield from final_events(response)
            return

        yield start_step("profile_result")
        profile_step, profile_obs = execute_step("profile_result", "result.profile")
        yield complete_step(profile_step)
        yield from append_artifacts_from_observation("profile_result", profile_obs)

        yield start_step("suggest_chart")
        chart_step, chart_obs = execute_step("suggest_chart", "chart.suggest")
        yield complete_step(chart_step)
        yield from append_artifacts_from_observation("suggest_chart", chart_obs)

        yield start_step("suggest_followups")
        suggestions_step, suggestions_obs = execute_step("suggest_followups", "followup.suggest")
        yield complete_step(suggestions_step)

        yield start_step("answer_synthesizer")
        answer_step, answer_obs = execute_step("answer_synthesizer", "answer.synthesize")
        yield complete_step(answer_step)
        if state.answer:
            explanation = str(state.answer.get("answer") or "")

        response = self._response(
            req=req,
            success=True,
            steps=steps,
            query_plan=state.query_plan,
            sql=safe_sql,
            safety=safety,
            execution=state.execution,
            explanation=explanation,
            chart_suggestion=state.chart_suggestion,
            result_profile=state.result_profile,
            answer=state.answer,
            suggestions=state.suggestions,
            error=None,
            run_id=run_id,
            session_id=run.session_id,
            artifacts=artifacts,
            artifact_identity=artifact_identity,
        )
        yield from final_events(response)

    def _workspace_tool_name(self, plan: AgentPlanDraft) -> str | None:
        expected = WORKSPACE_TOOL_BY_INTENT.get(plan.intent.intent)
        if not expected:
            return None
        planned = {step.tool_name for step in plan.steps}
        return expected if expected in planned else None

    def _workspace_answer_payload(self, output: dict[str, Any]) -> dict[str, Any]:
        raw_suggestions = output.get("suggestions")
        raw_safety_notes = output.get("safety_notes")
        safety_notes: list[Any] = raw_safety_notes if isinstance(raw_safety_notes, list) else []
        suggestions = [
            dict(item)
            for item in (raw_suggestions if isinstance(raw_suggestions, list) else [])
            if isinstance(item, dict)
        ]
        recommendations = [
            str(item.get("title") or item.get("explanation") or "")
            for item in suggestions
            if str(item.get("title") or item.get("explanation") or "").strip()
        ]
        evidence: list[dict[str, Any]] = []
        if suggestions or output.get("proposed_sql"):
            evidence.append(
                {
                    "artifact_id": "sql_suggestion",
                    "label": "SQL suggestion",
                    "value": suggestions[0].get("title") if suggestions else "workspace suggestion",
                }
            )
        return {
            "answer": str(output.get("answer") or "Workspace assistance completed."),
            "key_findings": [],
            "evidence": evidence,
            "caveats": [str(item) for item in safety_notes],
            "recommendations": recommendations,
            "follow_up_questions": [],
        }

    def _record(self, steps: list[AgentStep], observation: ToolObservation) -> AgentStep:
        step = AgentStep(
            name=observation.name,
            status=observation.status,
            input=observation.input,
            output=observation.output,
            error=observation.error,
            latency_ms=observation.latency_ms,
        )
        steps.append(step)
        return step

    def _should_wait_for_approval(self, safety: dict[str, Any]) -> bool:
        blocked_reasons = {str(item) for item in (safety.get("blocked_reasons") or [])}
        requires_confirmation = bool(
            safety.get("requires_confirmation")
            or "requires_confirmation" in blocked_reasons
        )
        return requires_confirmation and not bool(blocked_reasons & APPROVAL_HARD_BLOCKERS)

    def _approval_risk_level(self, safety: dict[str, Any]) -> str:
        trust_gate = safety.get("trust_gate") if isinstance(safety.get("trust_gate"), dict) else {}
        risk = str(trust_gate.get("riskLevel") or safety.get("risk_level") or "warning")
        if risk == "safe" and self._should_wait_for_approval(safety):
            return "warning"
        return risk if risk in {"safe", "warning", "danger"} else "warning"

    def _approval_reason(self, safety: dict[str, Any]) -> str | None:
        messages = safety.get("messages") if isinstance(safety.get("messages"), list) else []
        for message in messages:
            text = str(message).strip()
            if text:
                return text
        suggestion = str(safety.get("revise_suggestion") or "").strip()
        return suggestion or "Manual approval is required before executing this SQL."

    def _policy_decision(self, safety: dict[str, Any]) -> dict[str, Any]:
        decision = safety.get("execution_safety_decision")
        return dict(decision) if isinstance(decision, dict) else dict(safety)

    def _requested_action(
        self,
        req: AgentRunRequest,
        state: AgentState,
        sql: str | None,
    ) -> dict[str, Any]:
        safety = state.safety or {}
        decision = safety.get("execution_safety_decision") if isinstance(safety.get("execution_safety_decision"), dict) else {}
        return {
            "tool_name": "sql.execute_readonly",
            "datasource_id": req.datasource_id,
            "question": req.question,
            "sql": state.sql or sql,
            "safe_sql": safety.get("safe_sql") or decision.get("safe_sql") or state.sql or sql,
        }

    def _pending_step_specs(self, req: AgentRunRequest, after_step: str) -> list[dict[str, Any]]:
        plan = self.build_default_plan(req)
        start_index = 0
        for index, step in enumerate(plan):
            if step.name == after_step:
                start_index = index + 1
                break
        return [step.model_dump(mode="json") for step in plan[start_index:]]

    def _approve_safety_for_execution(self, state: AgentState, approval: AgentApprovalRecord) -> str:
        safety = state.safety or {}
        blocked_reasons = {str(item) for item in (safety.get("blocked_reasons") or [])}
        if blocked_reasons & APPROVAL_HARD_BLOCKERS:
            raise DataBoxError("Approval cannot override hard safety blockers.", code="APPROVAL_HARD_BLOCKED")

        decision = safety.get("execution_safety_decision") if isinstance(safety.get("execution_safety_decision"), dict) else {}
        safe_sql = str(
            decision.get("safe_sql")
            or safety.get("safe_sql")
            or state.sql
            or decision.get("original_sql")
            or ""
        ).strip()
        if not safe_sql:
            raise DataBoxError("Checkpoint does not contain executable SQL.", code="CHECKPOINT_SQL_MISSING")

        approved_blockers = [reason for reason in (safety.get("blocked_reasons") or []) if reason != "requires_confirmation"]
        messages = [str(message) for message in (safety.get("messages") or [])]
        messages.append(f"Agent approval {approval.id} approved execution after manual review.")

        if isinstance(decision, dict):
            decision["safe_sql"] = safe_sql
            decision["can_execute"] = True
            decision["passed"] = True
            decision["requires_confirmation"] = False
            decision["blocked_reasons"] = [reason for reason in (decision.get("blocked_reasons") or []) if reason != "requires_confirmation"]
            decision["messages"] = messages
            scope_state = decision.get("scope_state") if isinstance(decision.get("scope_state"), dict) else {}
            scope_state["agent_approval_id"] = approval.id
            decision["scope_state"] = scope_state
            safety["execution_safety_decision"] = decision

        safety["safe_sql"] = safe_sql
        safety["can_execute"] = not approved_blockers
        safety["passed"] = not approved_blockers
        safety["requires_confirmation"] = False
        safety["blocked_reasons"] = approved_blockers
        safety["messages"] = messages
        safety["approval"] = {
            "id": approval.id,
            "status": approval.status,
            "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
        }
        state.safety = safety
        state.sql = safe_sql
        return safe_sql

    def _budget_reached(self, req: AgentRunRequest, steps: list[AgentStep]) -> bool:
        return len(steps) >= req.max_steps

    def _attach_generation_notes(self, safety: dict[str, Any], sql_output: dict[str, Any]) -> None:
        rewrite_notes = list(sql_output.get("rewrite_notes") or [])
        raw_metadata = sql_output.get("metadata")
        metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
        raw_rewrite_metadata = metadata.get("rewrite")
        rewrite_metadata: dict[str, Any] = raw_rewrite_metadata if isinstance(raw_rewrite_metadata, dict) else {}
        safety["rewrite_notes"] = rewrite_notes
        safety["generation_metadata"] = metadata
        messages = safety.setdefault("messages", [])
        if not isinstance(messages, list):
            messages = []
            safety["messages"] = messages
        if rewrite_metadata.get("message"):
            messages.append(str(rewrite_metadata["message"]))

    def _response(
        self,
        req: AgentRunRequest,
        success: bool,
        steps: list[AgentStep],
        query_plan: dict[str, Any] | None,
        sql: str | None,
        safety: dict[str, Any] | None,
        execution: dict[str, Any] | None,
        explanation: str | None,
        chart_suggestion: dict[str, Any] | None,
        result_profile: dict[str, Any] | None,
        answer: dict[str, Any] | None,
        suggestions: list[dict[str, Any]],
        error: str | None,
        run_id: str | None = None,
        session_id: str | None = None,
        artifacts: list[AgentArtifact] | None = None,
        artifact_identity: AgentArtifactIdentity | None = None,
        status: str | None = None,
        approval: AgentApprovalRecord | None = None,
        checkpoint: AgentCheckpointRecord | None = None,
    ) -> AgentRunResponse:
        parsed_profile = ResultProfile.model_validate(result_profile) if result_profile else None
        parsed_suggestions = [
            FollowUpSuggestion.model_validate(item)
            for item in suggestions
            if isinstance(item, dict)
        ]
        parsed_answer = AgentAnswer.model_validate(answer) if answer else None
        if parsed_answer is None and (error or success):
            parsed_answer = synthesize_agent_answer(
                question=req.question,
                query_plan=query_plan,
                sql=sql,
                safety=safety,
                execution=execution,
                result_profile=parsed_profile,
                suggestions=parsed_suggestions,
                error=error,
            )
            explanation = explanation or parsed_answer.answer

        response_artifacts = self._response_artifacts(
            artifacts=artifacts,
            query_plan=query_plan,
            sql=sql,
            safety=safety,
            execution=execution,
            chart_suggestion=chart_suggestion,
            result_profile=parsed_profile,
            answer=parsed_answer,
            error=error,
            run_id=run_id,
            artifact_identity=artifact_identity,
        )
        if parsed_answer is not None:
            self._bind_answer_evidence(parsed_answer, response_artifacts)
        events = build_visible_events(
            question=req.question,
            steps=steps,
            artifacts=response_artifacts,
            answer=parsed_answer,
            suggestions=parsed_suggestions,
            error=error,
        )
        message_blocks = build_message_blocks(events)
        response_context_summary = build_response_context_summary(
            req=req,
            answer=parsed_answer.answer if parsed_answer else explanation,
            artifacts=response_artifacts,
        )

        response = AgentRunResponse(
            run_id=run_id or str(uuid.uuid4()),
            session_id=session_id or self._session_id(req),
            parent_run_id=req.parent_run_id or (req.follow_up_context.parent_run_id if req.follow_up_context else None),
            success=success,
            status=status or ("success" if success else "failed"),
            question=req.question,
            context_summary=response_context_summary,
            referenced_artifact_ids=referenced_artifact_ids(req),
            query_plan=query_plan,
            sql=sql,
            safety=safety,
            execution=execution,
            explanation=explanation,
            chart_suggestion=chart_suggestion,
            result_profile=parsed_profile,
            answer=parsed_answer,
            suggestions=parsed_suggestions,
            artifacts=response_artifacts,
            message_blocks=message_blocks,
            events=events,
            trace_events=build_trace_events(steps),
            steps=steps,
            error=error,
            approval=approval,
            checkpoint=checkpoint,
        )
        validate_agent_response_contract(response)
        return response

    def _response_artifacts(
        self,
        artifacts: list[AgentArtifact] | None,
        query_plan: dict[str, Any] | None,
        sql: str | None,
        safety: dict[str, Any] | None,
        execution: dict[str, Any] | None,
        chart_suggestion: dict[str, Any] | None,
        result_profile: ResultProfile | None,
        answer: AgentAnswer | None,
        error: str | None,
        run_id: str | None,
        artifact_identity: AgentArtifactIdentity | None,
    ) -> list[AgentArtifact]:
        identity = artifact_identity or AgentArtifactIdentity(run_id)
        if artifacts is None:
            response_artifacts = build_agent_artifacts(
                query_plan=query_plan,
                sql=sql,
                safety=safety,
                execution=execution,
                chart_suggestion=chart_suggestion,
                result_profile=result_profile,
                answer=answer,
                error=error,
                identity=identity,
            )
        else:
            response_artifacts = list(artifacts)
            semantic_ids = {artifact.semantic_id or artifact.id for artifact in response_artifacts}
            if answer and answer.recommendations and "recommendations" not in semantic_ids:
                response_artifacts.append(build_recommendations_artifact(answer, identity=identity))
                semantic_ids.add("recommendations")
            if error and "agent_error" not in semantic_ids:
                response_artifacts.append(
                    build_error_artifact(error, safety=safety, execution=execution, identity=identity)
                )

        self._bind_artifact_dependencies(response_artifacts)
        return response_artifacts

    def _bind_answer_evidence(self, answer: AgentAnswer, artifacts: list[AgentArtifact]) -> None:
        semantic_to_id = {artifact.semantic_id or artifact.id: artifact.id for artifact in artifacts}
        artifact_ids = {artifact.id for artifact in artifacts}
        answer.evidence = [
            evidence if evidence.artifact_id in artifact_ids else evidence.model_copy(
                update={"artifact_id": semantic_to_id.get(evidence.artifact_id, evidence.artifact_id)}
            )
            for evidence in answer.evidence
        ]

    def _bind_artifact_dependencies(self, artifacts: list[AgentArtifact]) -> None:
        semantic_to_id = {artifact.semantic_id or artifact.id: artifact.id for artifact in artifacts}
        for artifact in artifacts:
            artifact.depends_on = [semantic_to_id.get(dependency, dependency) for dependency in artifact.depends_on]

    def _failure(
        self,
        req: AgentRunRequest,
        steps: list[AgentStep],
        error: str,
        query_plan: dict[str, Any] | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        artifacts: list[AgentArtifact] | None = None,
        artifact_identity: AgentArtifactIdentity | None = None,
    ) -> AgentRunResponse:
        return self._response(
            req=req,
            success=False,
            steps=steps,
            query_plan=query_plan,
            sql=None,
            safety=None,
            execution=None,
            explanation=None,
            chart_suggestion=None,
            result_profile=None,
            answer=None,
            suggestions=[],
            error=error,
            run_id=run_id,
            session_id=session_id,
            artifacts=artifacts,
            artifact_identity=artifact_identity,
        )

    def _session_id(self, req: AgentRunRequest) -> str:
        if req.session_id:
            return req.session_id
        if req.follow_up_context and req.follow_up_context.session_id:
            return req.follow_up_context.session_id
        return str(uuid.uuid4())
