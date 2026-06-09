from __future__ import annotations

import logging
from typing import Any
from langchain_core.runnables import RunnableConfig

from engine.agent.types import ToolObservation
from engine.agent_kernel.databinding import apply_tool_result_to_state
from engine.databox_agent.graph.state import DataBoxAgentState
from engine.agent import persistence as ap
from engine.agent.artifacts import (
    AgentArtifactIdentity,
    build_chart_artifact,
    build_sql_suggestion_artifact,
    build_profile_artifact,
    build_query_plan_artifact,
    build_safety_artifact,
    build_sql_artifact,
    build_table_artifact,
)
from engine.agent.types import ResultProfile

logger = logging.getLogger("databox.databox_agent.nodes.observe_node")


def _tool_name_from_step(step_name: str) -> str:
    mapping = {
        "load_follow_up_context": "followup.load_context",
        "build_schema_context": "schema.build_context",
        "build_query_plan": "query_plan.build",
        "generate_sql_candidate": "sql.generate",
        "validate_sql": "sql.validate",
        "execute_sql": "sql.execute_readonly",
        "revise_sql": "sql.revise",
        "profile_result": "result.profile",
        "suggest_chart": "chart.suggest",
        "suggest_followups": "followup.suggest",
        "answer_synthesizer": "answer.synthesize",
    }
    return mapping.get(step_name, step_name)


def emit_artifacts_from_observation(
    step_name: str,
    observation: ToolObservation,
    state: dict[str, Any],
    run_id: str,
) -> list[Any]:
    if observation.status == "failed":
        return []

    identity = AgentArtifactIdentity(run_id)
    artifacts = []

    if step_name == "build_query_plan" and state.get("query_plan"):
        artifacts.append(build_query_plan_artifact(state["query_plan"], identity=identity))

    if step_name == "validate_sql" and state.get("sql") and state.get("safety"):
        artifacts.append(build_sql_artifact(state["sql"], safety=state["safety"], identity=identity))
        artifacts.append(build_safety_artifact(state["safety"], identity=identity))

    if step_name == "execute_sql" and state.get("execution") and state.get("execution", {}).get("success"):
        artifacts.append(build_table_artifact(state["execution"], safety=state.get("safety"), identity=identity))

    if step_name == "profile_result" and state.get("result_profile"):
        parsed_profile = ResultProfile.model_validate(state["result_profile"])
        artifacts.append(
            build_profile_artifact(
                parsed_profile,
                execution=state.get("execution"),
                safety=state.get("safety"),
                identity=identity,
            )
        )

    if (
        step_name == "suggest_chart"
        and state.get("chart_suggestion")
        and state.get("chart_suggestion", {}).get("type")
        and state.get("chart_suggestion", {}).get("type") != "table"
    ):
        artifacts.append(build_chart_artifact(state["chart_suggestion"], safety=state.get("safety"), identity=identity))

    if step_name.startswith("workspace.") and observation.output:
        payload = dict(observation.output)
        payload["produced_by_step"] = step_name
        artifacts.append(build_sql_suggestion_artifact(payload, identity=identity))

    # Bind dependencies
    existing_artifacts = state.get("artifacts") or []
    semantic_to_id = {}
    for item in existing_artifacts:
        if isinstance(item, dict):
            sem_id = item.get("semantic_id") or item.get("id")
            item_id = item.get("id")
        else:
            sem_id = item.semantic_id or item.id
            item_id = item.id
        if sem_id and item_id:
            semantic_to_id[sem_id] = item_id

    for art in artifacts:
        art.depends_on = [semantic_to_id.get(dep, dep) for dep in art.depends_on]

    return artifacts


def observe_tools(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable") or {}
    db = configurable.get("db")
    run_id = state.get("run_id") or ""
    thread_id = state.get("thread_id") or state.get("run_id") or ""

    last_tool_results = state.get("last_tool_results") or []

    state_updates: dict[str, Any] = {}
    temp_state = dict(state)

    new_artifacts_dicts = []

    for result_dict in last_tool_results:
        obs = ToolObservation.model_validate(result_dict)
        step_name = obs.name
        tool_name = _tool_name_from_step(step_name)

        databinding_updates = apply_tool_result_to_state(
            state=temp_state,
            tool_name=tool_name,
            observation=obs,
        )

        # Remove the legacy dict artifacts built by standard databinding
        databinding_updates.pop("artifacts", None)

        temp_state.update(databinding_updates)
        
        # Merge updates (accumulating lists)
        for k, v in databinding_updates.items():
            if k in {"tool_results", "trace_events"}:
                state_updates.setdefault(k, []).extend(v)
            else:
                state_updates[k] = v

        artifacts = emit_artifacts_from_observation(step_name, obs, temp_state, run_id)
        if artifacts:
            for art in artifacts:
                art_dict = art.model_dump(mode="json")
                new_artifacts_dicts.append(art_dict)
                if db is not None:
                    try:
                        from engine.models import AgentArtifactRecord
                        existing_count = db.query(AgentArtifactRecord).filter(
                            AgentArtifactRecord.run_id == run_id
                        ).count()
                        ap.record_artifact(db, thread_id, run_id, art, sequence=existing_count + 1)
                    except Exception as exc:
                        logger.warning("Failed to save artifact %s to DB: %s", art.id, exc)

    if new_artifacts_dicts:
        state_updates["artifacts"] = new_artifacts_dicts

    return state_updates
