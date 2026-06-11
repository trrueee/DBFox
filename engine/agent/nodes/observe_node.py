from __future__ import annotations

import logging
from typing import Any
from langchain_core.runnables import RunnableConfig

from engine.agent_core.types import ToolObservation
from engine.agent_core.databinding import apply_tool_result_to_state
from engine.agent.graph.state import DataBoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent_core import persistence as ap
from engine.agent_core.artifacts import (
    AgentArtifactIdentity,
    build_chart_artifact,
    build_recommendations_artifact,
    build_semantic_resolution_artifact,
    build_sql_suggestion_artifact,
    build_profile_artifact,
    build_query_plan_artifact,
    build_safety_artifact,
    build_sql_artifact,
    build_table_artifact,
)
from engine.agent_core.types import AgentAnswer, ResultProfile

logger = logging.getLogger("databox.databox_agent.nodes.observe_node")


def _tool_name_from_step(step_name: str) -> str:
    mapping = {
        "load_follow_up_context": "followup.load_context",
        "build_schema_context": "schema.build_context",
        "build_query_plan": "query_plan.build",
        "generate_sql_candidate": "sql.generate",
        "validate_sql": "sql.validate",
        "execute_sql": "sql.execute_readonly",
        "skip_execution": "sql.skip_execution",
        "revise_sql": "sql.revise",
        "profile_result": "result.profile",
        "suggest_chart": "chart.suggest",
        "suggest_followups": "followup.suggest",
        "answer_synthesizer": "answer.synthesize",
        "analysis_compose": "analysis.compose",
    }
    return mapping.get(step_name, step_name)


def _derive_query_plan(state: dict[str, Any], observation: ToolObservation) -> dict[str, Any] | None:
    """Best-effort query plan when no query_plan.build step ran.

    Prefers the plan embedded in the SQL generator's metadata, falling back to
    a minimal plan assembled from the question and schema context.
    """
    candidate = state.get("sql_candidate") or {}
    meta = candidate.get("metadata") if isinstance(candidate, dict) and isinstance(candidate.get("metadata"), dict) else {}

    for key in ("query_plan", "agent_query_plan"):
        plan = meta.get(key)
        if isinstance(plan, dict) and plan:
            return plan

    question = ""
    if isinstance(observation.input, dict):
        question = str(observation.input.get("question") or "")

    schema_ctx = state.get("schema_context") or {}
    candidate_tables = schema_ctx.get("selected_tables") if isinstance(schema_ctx, dict) else None
    if not isinstance(candidate_tables, list):
        candidate_tables = meta.get("selected_tables") if isinstance(meta.get("selected_tables"), list) else []

    if not question and not candidate_tables:
        return None

    return {
        "analysis_goal": question,
        "candidate_tables": [str(t) for t in candidate_tables],
        "metrics": [],
        "dimensions": [],
        "filters": [],
        "derived_from": "sql_generate",
    }


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

    if step_name == "generate_sql_candidate" and not state.get("query_plan"):
        # The model skipped the explicit query_plan.build step (the generator can
        # work directly from schema context). Still surface a query_plan artifact
        # so the UI/persistence layer always has the plan-level view of the run.
        plan = _derive_query_plan(state, observation)
        if plan:
            artifacts.append(build_query_plan_artifact(plan, identity=identity))

    if step_name == "semantic.resolve" and state.get("semantic_resolution"):
        artifacts.append(build_semantic_resolution_artifact(state["semantic_resolution"], identity=identity))

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

    if step_name == "analysis_compose" and state.get("answer"):
        answer = AgentAnswer.model_validate(state["answer"])
        if answer.recommendations or answer.follow_up_questions:
            artifacts.append(build_recommendations_artifact(answer, identity=identity))

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
    ctx = graph_context(config)
    db = ctx.db
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

    # ---- Rebuild ContextPack (Agent v2) ------------------------------------
    try:
        from engine.agent.context_pack import build_context_pack
        merged_state = dict(state)
        merged_state.update(state_updates)
        state_updates["context_pack"] = build_context_pack(merged_state).model_dump(mode="json")
    except Exception as exc:
        logger.warning("Failed to build ContextPack: %s", exc)

    return state_updates
