from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from engine.agent.tools import (
    build_query_plan_tool,
    build_schema_context_tool,
    execute_sql_tool,
    explain_result_tool,
    generate_sql_tool,
    revise_sql_tool,
    skipped_execute_observation,
    suggest_chart_tool,
    validate_sql_tool,
)
from engine.agent.types import AgentRunRequest, AgentRunResponse, AgentStep, ToolObservation


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

        schema_obs = build_schema_context_tool(self.db, req)
        self._record(steps, schema_obs)
        if schema_obs.status == "failed":
            return self._failure(req, steps, "Failed to build schema context.")

        schema_context = schema_obs.output or {}

        plan_obs = build_query_plan_tool(self.db, req, schema_context)
        self._record(steps, plan_obs)
        if plan_obs.status == "failed":
            return self._failure(req, steps, "Failed to build query plan.")
        query_plan = plan_obs.output

        sql_obs = generate_sql_tool(self.db, req)
        self._record(steps, sql_obs)
        if sql_obs.status == "failed":
            revise_obs = revise_sql_tool(None, sql_obs.error or "SQL generation failed.")
            self._record(steps, revise_obs)
            return self._failure(req, steps, sql_obs.error or "Failed to generate SQL.", query_plan=query_plan)

        sql_output = sql_obs.output or {}
        sql = str(sql_output.get("sql") or "").strip()
        if not sql:
            revise_obs = revise_sql_tool(sql, "SQL generation returned an empty candidate.")
            self._record(steps, revise_obs)
            return self._failure(req, steps, "SQL generation returned an empty candidate.", query_plan=query_plan)

        validate_obs = validate_sql_tool(self.db, req.datasource_id, sql)
        self._record(steps, validate_obs)
        safety = validate_obs.output or {}
        if validate_obs.status == "failed" or not safety.get("can_execute"):
            reason = (
                safety.get("revise_suggestion")
                or validate_obs.error
                or "SQL did not pass DataBox Agent validation."
            )
            revise_obs = revise_sql_tool(sql, str(reason), safety)
            self._record(steps, revise_obs)
            return AgentRunResponse(
                success=False,
                question=req.question,
                query_plan=query_plan,
                sql=sql,
                safety=safety,
                execution=None,
                explanation=None,
                chart_suggestion=None,
                steps=steps,
                error=str(reason),
            )

        safe_sql = str(safety.get("safe_sql") or sql)
        sql = safe_sql

        if req.execute:
            execute_obs = execute_sql_tool(self.db, req, safe_sql)
            self._record(steps, execute_obs)
            execution = execute_obs.output or {}
            if execute_obs.status == "failed":
                reason = (
                    execution.get("revise_suggestion")
                    or execute_obs.error
                    or "SQL execution failed."
                )
                revise_obs = revise_sql_tool(safe_sql, str(reason), safety)
                self._record(steps, revise_obs)
                return AgentRunResponse(
                    success=False,
                    question=req.question,
                    query_plan=query_plan,
                    sql=safe_sql,
                    safety=safety,
                    execution=execution,
                    explanation=None,
                    chart_suggestion=None,
                    steps=steps,
                    error=str(reason),
                )
        else:
            execute_obs = skipped_execute_observation()
            self._record(steps, execute_obs)
            execution = execute_obs.output

        explain_obs = explain_result_tool(req, safe_sql, query_plan, execution, safety)
        self._record(steps, explain_obs)
        if explain_obs.output:
            explanation = str(explain_obs.output.get("explanation") or "")

        chart_obs = suggest_chart_tool(execution)
        self._record(steps, chart_obs)
        chart_suggestion = chart_obs.output

        return AgentRunResponse(
            success=True,
            question=req.question,
            query_plan=query_plan,
            sql=safe_sql,
            safety=safety,
            execution=execution,
            explanation=explanation,
            chart_suggestion=chart_suggestion,
            steps=steps,
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

    def _failure(
        self,
        req: AgentRunRequest,
        steps: list[AgentStep],
        error: str,
        query_plan: dict[str, Any] | None = None,
    ) -> AgentRunResponse:
        return AgentRunResponse(
            success=False,
            question=req.question,
            query_plan=query_plan,
            sql=None,
            safety=None,
            execution=None,
            explanation=None,
            chart_suggestion=None,
            steps=steps,
            error=error,
        )
