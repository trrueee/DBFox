from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from engine.agent.answer import synthesize_agent_answer
from engine.agent.artifacts import build_agent_artifacts
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
    AgentStep,
    FollowUpSuggestion,
    ResultProfile,
    ToolObservation,
)


class DataBoxAgentRuntime:
    def __init__(self, db: Session):
        self.db = db

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        steps: list[AgentStep] = []
        query_plan: dict[str, Any] | None = None
        sql: str | None = None
        safety: dict[str, Any] | None = None
        execution: dict[str, Any] | None = None
        explanation: str | None = None
        chart_suggestion: dict[str, Any] | None = None
        result_profile: dict[str, Any] | None = None
        answer: dict[str, Any] | None = None
        suggestions: list[dict[str, Any]] = []

        if has_follow_up_context(req):
            context_obs = load_followup_context_tool(req)
            self._record(steps, context_obs)
            if context_obs.status == "failed":
                return self._failure(req, steps, "Failed to load follow-up context.")
            if self._budget_reached(req, steps):
                return self._failure(req, steps, "Agent stopped before schema linking because max_steps was reached.")

        schema_obs = build_schema_context_tool(self.db, req)
        self._record(steps, schema_obs)
        if schema_obs.status == "failed":
            return self._failure(req, steps, "Failed to build schema context.")

        schema_context = schema_obs.output or {}

        if self._budget_reached(req, steps):
            return self._failure(req, steps, "Agent stopped before query planning because max_steps was reached.")

        plan_obs = build_query_plan_tool(self.db, req, schema_context)
        self._record(steps, plan_obs)
        if plan_obs.status == "failed":
            return self._failure(req, steps, "Failed to build query plan.")
        query_plan = plan_obs.output

        if self._budget_reached(req, steps):
            return self._failure(req, steps, "Agent stopped before SQL generation because max_steps was reached.", query_plan=query_plan)

        sql_obs = generate_sql_tool(self.db, req, schema_context=schema_context, query_plan=query_plan)
        self._record(steps, sql_obs)
        if sql_obs.status == "failed":
            revise_obs = revise_sql_tool(
                None,
                sql_obs.error or "SQL generation failed.",
                db=self.db,
                datasource_id=req.datasource_id,
            )
            self._record(steps, revise_obs)
            return self._failure(req, steps, sql_obs.error or "Failed to generate SQL.", query_plan=query_plan)

        sql_output = sql_obs.output or {}
        sql = str(sql_output.get("sql") or "").strip()
        if not sql:
            revise_obs = revise_sql_tool(
                sql,
                "SQL generation returned an empty candidate.",
                db=self.db,
                datasource_id=req.datasource_id,
            )
            self._record(steps, revise_obs)
            return self._failure(req, steps, "SQL generation returned an empty candidate.", query_plan=query_plan)

        if self._budget_reached(req, steps):
            return self._failure(req, steps, "Agent stopped before SQL validation because max_steps was reached.", query_plan=query_plan)

        validate_obs = validate_sql_tool(self.db, req.datasource_id, sql)
        self._record(steps, validate_obs)
        safety = validate_obs.output or {}
        self._attach_generation_notes(safety, sql_output)
        if validate_obs.status == "failed" or not safety.get("can_execute"):
            reason = (
                safety.get("revise_suggestion")
                or validate_obs.error
                or "SQL did not pass DataBox Agent validation."
            )
            revise_obs = revise_sql_tool(sql, str(reason), safety, db=self.db, datasource_id=req.datasource_id)
            self._record(steps, revise_obs)
            return self._response(
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
            )

        safe_sql = str(safety.get("safe_sql") or sql)
        sql = safe_sql

        if req.execute:
            if self._budget_reached(req, steps):
                return self._response(
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
                )

            execute_obs = execute_sql_tool(self.db, req, safe_sql, safety=safety)
            self._record(steps, execute_obs)
            execution = execute_obs.output or {}
            if execute_obs.status == "failed":
                reason = (
                    execution.get("revise_suggestion")
                    or execute_obs.error
                    or "SQL execution failed."
                )
                revise_obs = revise_sql_tool(safe_sql, str(reason), safety, db=self.db, datasource_id=req.datasource_id)
                self._record(steps, revise_obs)
                return self._response(
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
                )
        else:
            execute_obs = skipped_execute_observation()
            self._record(steps, execute_obs)
            execution = execute_obs.output

        if not self._budget_reached(req, steps):
            profile_obs = profile_result_tool(req, query_plan, execution)
            self._record(steps, profile_obs)
            if profile_obs.output:
                result_profile = profile_obs.output

        if not self._budget_reached(req, steps):
            chart_obs = suggest_chart_tool(execution)
            self._record(steps, chart_obs)
            chart_suggestion = chart_obs.output

        if not self._budget_reached(req, steps):
            suggestions_obs = suggest_followups_tool(req, safe_sql, safety, execution, result_profile, chart_suggestion)
            self._record(steps, suggestions_obs)
            if suggestions_obs.output:
                raw_suggestions = suggestions_obs.output.get("suggestions")
                suggestions = [dict(item) for item in raw_suggestions if isinstance(item, dict)] if isinstance(raw_suggestions, list) else []

        if not self._budget_reached(req, steps):
            answer_obs = answer_synthesizer_tool(
                req,
                query_plan=query_plan,
                sql=safe_sql,
                safety=safety,
                execution=execution,
                result_profile=result_profile,
                suggestions=suggestions,
            )
            self._record(steps, answer_obs)
            if answer_obs.output:
                answer = answer_obs.output
                explanation = str(answer.get("answer") or "")

        return self._response(
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
        )

    def _record(self, steps: list[AgentStep], observation: ToolObservation) -> None:
        steps.append(
            AgentStep(
                name=observation.name,
                status=observation.status,
                input=observation.input,
                output=observation.output,
                error=observation.error,
                latency_ms=observation.latency_ms,
            )
        )

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

        artifacts = build_agent_artifacts(
            query_plan=query_plan,
            sql=sql,
            safety=safety,
            execution=execution,
            chart_suggestion=chart_suggestion,
            result_profile=parsed_profile,
            answer=parsed_answer,
            error=error,
        )
        events = build_visible_events(
            question=req.question,
            steps=steps,
            artifacts=artifacts,
            answer=parsed_answer,
            suggestions=parsed_suggestions,
            error=error,
        )
        message_blocks = build_message_blocks(events)
        response_context_summary = build_response_context_summary(
            req=req,
            answer=parsed_answer.answer if parsed_answer else explanation,
            artifacts=artifacts,
        )

        response = AgentRunResponse(
            run_id=str(uuid.uuid4()),
            session_id=self._session_id(req),
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
            artifacts=artifacts,
            message_blocks=message_blocks,
            events=events,
            trace_events=build_trace_events(steps),
            steps=steps,
            error=error,
        )
        validate_agent_response_contract(response)
        return response

    def _failure(
        self,
        req: AgentRunRequest,
        steps: list[AgentStep],
        error: str,
        query_plan: dict[str, Any] | None = None,
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
        )

    def _session_id(self, req: AgentRunRequest) -> str:
        if req.session_id:
            return req.session_id
        if req.follow_up_context and req.follow_up_context.session_id:
            return req.follow_up_context.session_id
        return str(uuid.uuid4())
