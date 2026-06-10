from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from engine.agent_core.types import AgentArtifact, AgentStep, ToolObservation


class AgentState(BaseModel):
    run_id: str
    session_id: str | None = None
    parent_run_id: str | None = None
    question: str
    datasource_id: str

    follow_up_context: dict[str, Any] | None = None
    schema_context: str | None = None
    schema_metadata: dict[str, Any] = Field(default_factory=dict)

    query_plan: dict[str, Any] | None = None
    sql: str | None = None
    sql_candidate: dict[str, Any] | None = None
    safety: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    result_profile: dict[str, Any] | None = None
    chart_suggestion: dict[str, Any] | None = None
    suggestions: list[dict[str, Any]] = Field(default_factory=list)
    answer: dict[str, Any] | None = None

    artifacts: list[AgentArtifact] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)

    def apply_observation(
        self,
        step_name: str,
        observation: ToolObservation,
        agent_step: AgentStep | None = None,
    ) -> None:
        self.steps.append(
            agent_step
            or AgentStep(
                name=observation.name or step_name,
                status=observation.status,
                input=observation.input,
                output=observation.output,
                error=observation.error,
                latency_ms=observation.latency_ms,
            )
        )

        output = observation.output or {}
        if observation.status == "failed" and not output:
            return

        if step_name == "load_follow_up_context":
            self.follow_up_context = output
        elif step_name == "build_schema_context":
            self.schema_metadata = output
            self.schema_context = str(output.get("schema_context") or "")
        elif step_name == "build_query_plan":
            self.query_plan = output
        elif step_name == "generate_sql_candidate":
            self.sql_candidate = output
            sql = str(output.get("sql") or "").strip()
            self.sql = sql or self.sql
        elif step_name == "validate_sql":
            self.safety = output
            safe_sql = str(output.get("safe_sql") or "").strip()
            self.sql = safe_sql or self.sql
        elif step_name == "execute_sql":
            self.execution = output
        elif step_name == "profile_result":
            self.result_profile = output
        elif step_name == "suggest_chart":
            self.chart_suggestion = output
        elif step_name == "suggest_followups":
            raw_suggestions = output.get("suggestions")
            if isinstance(raw_suggestions, list):
                self.suggestions = [dict(item) for item in raw_suggestions if isinstance(item, dict)]
        elif step_name == "answer_synthesizer":
            self.answer = output
