from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from engine.agent import persistence as agent_persistence
from engine.agent.answer import synthesize_agent_answer
from engine.agent.artifacts import (
    AgentArtifactIdentity,
    build_agent_artifacts,
    build_chart_artifact,
    build_error_artifact,
    build_profile_artifact,
    build_query_plan_artifact,
    build_recommendations_artifact,
    build_safety_artifact,
    build_sql_artifact,
    build_table_artifact,
)
from engine.agent.context import build_response_context_summary, has_follow_up_context, referenced_artifact_ids
from engine.agent.events import build_trace_events
from engine.agent.narration import build_message_blocks, build_visible_events
from engine.agent.validation import validate_agent_response_contract
from engine.agent.tools import (
    answer_synthesizer_tool,
    build_query_plan_tool,
    build_schema_context_tool,
    execute_sql_tool,
    generate_sql_tool,
    load_followup_context_tool,
    profile_result_tool,
    revise_sql_tool,
    skipped_execute_observation,
    suggest_chart_tool,
    suggest_followups_tool,
    validate_sql_tool,
)
from engine.agent.types import (
    AgentAnswer,
    AgentArtifact,
    AgentRunRequest,
    AgentRunResponse,
    AgentRuntimeEvent,
    AgentRuntimeEventType,
    AgentStep,
    FollowUpSuggestion,
    ResultProfile,
    ToolObservation,
)

logger = logging.getLogger("databox.agent.runtime")


class DataBoxAgentRuntime:
    def __init__(self, db: Session):
        self.db = db

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        final_response: AgentRunResponse | None = None
        for event in self.run_iter(req):
            if event.response is not None:
                final_response = event.response
        if final_response is None:
            raise RuntimeError("Agent runtime completed without a final response.")
        return final_response

    def run_iter(self, req: AgentRunRequest) -> Iterator[AgentRuntimeEvent]:
        run_id = str(uuid.uuid4())
        session_id = self._session_id(req)

        if not has_follow_up_context(req) and req.parent_run_id:
            reconstructed = agent_persistence.build_followup_context_from_run(self.db, req.parent_run_id)
            if reconstructed is not None:
                req.follow_up_context = reconstructed
                if not req.session_id:
                    req.session_id = reconstructed.session_id
                    session_id = reconstructed.session_id
        artifact_identity = AgentArtifactIdentity(run_id)
        sequence = 0
        steps: list[AgentStep] = []
        artifacts: list[AgentArtifact] = []
        emitted_artifact_ids: set[str] = set()
        query_plan: dict[str, Any] | None = None
        sql: str | None = None
        safety: dict[str, Any] | None = None
        execution: dict[str, Any] | None = None
        explanation: str | None = None
        chart_suggestion: dict[str, Any] | None = None
        result_profile: dict[str, Any] | None = None
        answer: dict[str, Any] | None = None
        suggestions: list[dict[str, Any]] = []

        def emit(
            event_type: AgentRuntimeEventType,
            *,
            step: dict[str, Any] | None = None,
            artifact: AgentArtifact | None = None,
            answer_payload: AgentAnswer | None = None,
            response: AgentRunResponse | None = None,
            error: str | None = None,
        ) -> AgentRuntimeEvent:
            nonlocal sequence
            sequence += 1
            event = AgentRuntimeEvent(
                event_id=f"runtime_{run_id[:8]}_{sequence}_{event_type.replace('.', '_')}",
                run_id=run_id,
                sequence=sequence,
                created_at_ms=int(time.time() * 1000),
                type=event_type,
                step=step,
                artifact=artifact,
                answer=answer_payload,
                response=response,
                error=error,
            )
            _save_event(event)
            return event

        def _save_event(event: AgentRuntimeEvent) -> None:
            try:
                agent_persistence.record_runtime_event(self.db, session_id, event)
            except Exception:
                logger.warning("Persistence: failed to save event %s", event.event_id)
                try:
                    self.db.rollback()
                except Exception:
                    pass

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

        def complete_step(observation: ToolObservation) -> AgentRuntimeEvent:
            step = self._record(steps, observation)
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
            except Exception:
                logger.warning("Persistence: failed to persist final response for run %s", run_id)
                try:
                    self.db.rollback()
                except Exception:
                    pass

        def append_artifact(artifact: AgentArtifact) -> AgentRuntimeEvent:
            semantic_to_id = {item.semantic_id or item.id: item.id for item in artifacts}
            artifact.depends_on = [semantic_to_id.get(dependency, dependency) for dependency in artifact.depends_on]
            artifacts.append(artifact)
            emitted_artifact_ids.add(artifact.id)
            event = emit("agent.artifact.created", artifact=artifact)
            _save_artifact_record(artifact, len(artifacts))
            return event

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

        if has_follow_up_context(req):
            yield start_step("load_follow_up_context")
            context_obs = load_followup_context_tool(req)
            yield complete_step(context_obs)
            if context_obs.status == "failed":
                yield from final_events(build_failure("Failed to load follow-up context."))
                return
            if self._budget_reached(req, steps):
                yield from final_events(build_failure("Agent stopped before schema linking because max_steps was reached."))
                return

        yield start_step("build_schema_context")
        schema_obs = build_schema_context_tool(self.db, req)
        yield complete_step(schema_obs)
        if schema_obs.status == "failed":
            yield from final_events(build_failure("Failed to build schema context."))
            return

        schema_context = schema_obs.output or {}

        if self._budget_reached(req, steps):
            yield from final_events(build_failure("Agent stopped before query planning because max_steps was reached."))
            return

        yield start_step("build_query_plan")
        plan_obs = build_query_plan_tool(self.db, req, schema_context)
        yield complete_step(plan_obs)
        if plan_obs.status == "failed":
            yield from final_events(build_failure("Failed to build query plan."))
            return
        query_plan = plan_obs.output
        if query_plan:
            yield append_artifact(build_query_plan_artifact(query_plan, identity=artifact_identity))

        if self._budget_reached(req, steps):
            yield from final_events(build_failure("Agent stopped before SQL generation because max_steps was reached.", query_plan))
            return

        yield start_step("generate_sql_candidate")
        sql_obs = generate_sql_tool(self.db, req, schema_context=schema_context, query_plan=query_plan)
        yield complete_step(sql_obs)
        if sql_obs.status == "failed":
            yield start_step("revise_sql")
            revise_obs = revise_sql_tool(
                None,
                sql_obs.error or "SQL generation failed.",
                db=self.db,
                datasource_id=req.datasource_id,
            )
            yield complete_step(revise_obs)
            yield from final_events(build_failure(sql_obs.error or "Failed to generate SQL.", query_plan))
            return

        sql_output = sql_obs.output or {}
        sql = str(sql_output.get("sql") or "").strip()
        if not sql:
            yield start_step("revise_sql")
            revise_obs = revise_sql_tool(
                sql,
                "SQL generation returned an empty candidate.",
                db=self.db,
                datasource_id=req.datasource_id,
            )
            yield complete_step(revise_obs)
            yield from final_events(build_failure("SQL generation returned an empty candidate.", query_plan))
            return

        if self._budget_reached(req, steps):
            yield from final_events(build_failure("Agent stopped before SQL validation because max_steps was reached.", query_plan))
            return

        yield start_step("validate_sql")
        validate_obs = validate_sql_tool(self.db, req.datasource_id, sql)
        yield complete_step(validate_obs)
        safety = validate_obs.output or {}
        self._attach_generation_notes(safety, sql_output)
        yield append_artifact(build_sql_artifact(sql, safety=safety, identity=artifact_identity))
        yield append_artifact(build_safety_artifact(safety, identity=artifact_identity))
        if validate_obs.status == "failed" or not safety.get("can_execute"):
            reason = (
                safety.get("revise_suggestion")
                or validate_obs.error
                or "SQL did not pass DataBox Agent validation."
            )
            yield start_step("revise_sql")
            revise_obs = revise_sql_tool(sql, str(reason), safety, db=self.db, datasource_id=req.datasource_id)
            yield complete_step(revise_obs)
            response = self._response(
                req=req,
                success=False,
                steps=steps,
                query_plan=query_plan,
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

        if req.execute:
            if self._budget_reached(req, steps):
                response = self._response(
                    req=req,
                    success=False,
                    steps=steps,
                    query_plan=query_plan,
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
            execute_obs = execute_sql_tool(self.db, req, safe_sql, safety=safety)
            yield complete_step(execute_obs)
            execution = execute_obs.output or {}
            if execute_obs.status != "failed" and execution.get("success"):
                yield append_artifact(build_table_artifact(execution, safety=safety, identity=artifact_identity))
            if execute_obs.status == "failed":
                reason = (
                    execution.get("revise_suggestion")
                    or execute_obs.error
                    or "SQL execution failed."
                )
                yield start_step("revise_sql")
                revise_obs = revise_sql_tool(safe_sql, str(reason), safety, db=self.db, datasource_id=req.datasource_id)
                yield complete_step(revise_obs)
                response = self._response(
                    req=req,
                    success=False,
                    steps=steps,
                    query_plan=query_plan,
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
            yield complete_step(execute_obs)
            execution = execute_obs.output

        if not self._budget_reached(req, steps):
            yield start_step("profile_result")
            profile_obs = profile_result_tool(req, query_plan, execution)
            yield complete_step(profile_obs)
            if profile_obs.output:
                result_profile = profile_obs.output
                parsed_profile = ResultProfile.model_validate(result_profile)
                yield append_artifact(build_profile_artifact(parsed_profile, safety=safety, identity=artifact_identity))

        if not self._budget_reached(req, steps):
            yield start_step("suggest_chart")
            chart_obs = suggest_chart_tool(execution)
            yield complete_step(chart_obs)
            chart_suggestion = chart_obs.output
            if chart_suggestion and chart_suggestion.get("type") and chart_suggestion.get("type") != "table":
                yield append_artifact(build_chart_artifact(chart_suggestion, safety=safety, identity=artifact_identity))

        if not self._budget_reached(req, steps):
            yield start_step("suggest_followups")
            suggestions_obs = suggest_followups_tool(req, safe_sql, safety, execution, result_profile, chart_suggestion)
            yield complete_step(suggestions_obs)
            if suggestions_obs.output:
                raw_suggestions = suggestions_obs.output.get("suggestions")
                suggestions = [dict(item) for item in raw_suggestions if isinstance(item, dict)] if isinstance(raw_suggestions, list) else []

        if not self._budget_reached(req, steps):
            yield start_step("answer_synthesizer")
            answer_obs = answer_synthesizer_tool(
                req,
                query_plan=query_plan,
                sql=safe_sql,
                safety=safety,
                execution=execution,
                result_profile=result_profile,
                suggestions=suggestions,
            )
            yield complete_step(answer_obs)
            if answer_obs.output:
                answer = answer_obs.output
                explanation = str(answer.get("answer") or "")

        response = self._response(
            req=req,
            success=True,
            steps=steps,
            query_plan=query_plan,
            sql=safe_sql,
            safety=safety,
            execution=execution,
            explanation=explanation,
            chart_suggestion=chart_suggestion,
            result_profile=result_profile,
            answer=answer,
            suggestions=suggestions,
            error=None,
            run_id=run_id,
            session_id=session_id,
            artifacts=artifacts,
            artifact_identity=artifact_identity,
        )
        yield from final_events(response)

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

    def _budget_reached(self, req: AgentRunRequest, steps: list[AgentStep]) -> bool:
        return len(steps) >= req.max_steps

    def _attach_generation_notes(self, safety: dict[str, Any], sql_output: dict[str, Any]) -> None:
        rewrite_notes = list(sql_output.get("rewrite_notes") or [])
        metadata = sql_output.get("metadata") if isinstance(sql_output.get("metadata"), dict) else {}
        rewrite_metadata = metadata.get("rewrite") if isinstance(metadata.get("rewrite"), dict) else {}
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
