from __future__ import annotations

from typing import Any

from engine.agent.artifacts import (
    AgentArtifactIdentity,
    build_agent_plan_artifact,
    build_chart_artifact,
    build_sql_suggestion_artifact,
    build_profile_artifact,
    build_query_plan_artifact,
    build_safety_artifact,
    build_sql_artifact,
    build_table_artifact,
)
from engine.agent.state import AgentState
from engine.agent.types import AgentArtifact, ResultProfile, ToolObservation


class ArtifactEmitter:
    def from_plan(
        self,
        plan: dict[str, Any],
        identity: AgentArtifactIdentity,
    ) -> list[AgentArtifact]:
        return [build_agent_plan_artifact(plan, identity=identity)]

    def from_observation(
        self,
        step_name: str,
        observation: ToolObservation,
        state: AgentState,
        identity: AgentArtifactIdentity,
    ) -> list[AgentArtifact]:
        if observation.status == "failed":
            return []

        if step_name == "build_query_plan" and state.query_plan:
            return [build_query_plan_artifact(state.query_plan, identity=identity)]

        if step_name == "validate_sql" and state.sql and state.safety:
            return [
                build_sql_artifact(state.sql, safety=state.safety, identity=identity),
                build_safety_artifact(state.safety, identity=identity),
            ]

        if step_name == "execute_sql" and state.execution and state.execution.get("success"):
            return [build_table_artifact(state.execution, safety=state.safety, identity=identity)]

        if step_name == "profile_result" and state.result_profile:
            parsed_profile = ResultProfile.model_validate(state.result_profile)
            return [build_profile_artifact(parsed_profile, execution=state.execution, safety=state.safety, identity=identity)]

        if (
            step_name == "suggest_chart"
            and state.chart_suggestion
            and state.chart_suggestion.get("type")
            and state.chart_suggestion.get("type") != "table"
        ):
            return [build_chart_artifact(state.chart_suggestion, safety=state.safety, identity=identity)]

        if step_name.startswith("workspace.") and observation.output:
            payload = dict(observation.output)
            payload["produced_by_step"] = step_name
            return [build_sql_suggestion_artifact(payload, identity=identity)]

        return []

    def bind_dependencies(self, artifacts: list[AgentArtifact], artifact: AgentArtifact) -> AgentArtifact:
        semantic_to_id = {item.semantic_id or item.id: item.id for item in artifacts}
        artifact.depends_on = [semantic_to_id.get(dependency, dependency) for dependency in artifact.depends_on]
        return artifact
