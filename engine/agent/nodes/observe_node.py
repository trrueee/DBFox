from __future__ import annotations

import logging
from typing import Any
from langchain_core.runnables import RunnableConfig

from engine.agent_core.types import ToolObservation
from engine.agent_core.databinding import apply_tool_result_to_state
from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent.progress.fast_path import _arg_signature
from engine.agent_core.artifacts import (
    AgentArtifactIdentity,
    build_chart_artifact,
    build_sql_suggestion_artifact,
    build_query_plan_artifact,
    build_safety_artifact,
    build_sql_artifact,
    build_result_view_artifact,
)
from engine.agent_core.chart_builder import is_chartable_suggestion

logger = logging.getLogger("dbfox.dbfox_agent.nodes.observe_node")


def _is_empty_result(tool_name: str, output: Any) -> bool:
    """Check whether a tool result is semantically empty (no data found)."""
    if not isinstance(output, dict):
        return False
    if tool_name == "db.search":
        results = output.get("results")
        return isinstance(results, list) and len(results) == 0
    if tool_name in ("schema.describe_table", "db.inspect"):
        return output.get("columns_count") == 0 or output.get("status") == "failed"
    if tool_name == "schema.list_tables_page":
        tbls = output.get("tables")
        return isinstance(tbls, list) and len(tbls) == 0
    if tool_name == "schema.expand_related_tables":
        rels = output.get("related_tables")
        return isinstance(rels, list) and len(rels) == 0
    return False


def _has_result_rows(payload: dict[str, Any]) -> bool:
    rows = payload.get("rows") or payload.get("previewRows")
    if isinstance(rows, list) and rows:
        return True
    for key in ("rowCount", "returnedRows", "returned_rows", "previewRowCount"):
        value = payload.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            return int(value) > 0
        except (TypeError, ValueError):
            continue
    return False


def _has_sql_suggestion_payload(payload: dict[str, Any]) -> bool:
    if isinstance(payload.get("proposed_sql"), str) and payload["proposed_sql"].strip():
        return True
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list):
        return False
    return any(
        isinstance(item, dict)
        and isinstance(item.get("proposed_sql"), str)
        and item["proposed_sql"].strip()
        for item in suggestions
    )


from engine.agent.tools.tool_aliases import STEP_NAME_TO_INTERNAL


def _tool_name_from_step(step_name: str) -> str:
    return STEP_NAME_TO_INTERNAL.get(step_name, step_name)


def _existing_artifact_id(state: dict[str, Any], semantic_id: str, artifact_type: str) -> str | None:
    for item in state.get("artifacts") or []:
        if isinstance(item, dict):
            item_id = item.get("id")
            item_semantic_id = item.get("semantic_id")
            item_type = item.get("type")
        else:
            item_id = getattr(item, "id", None)
            item_semantic_id = getattr(item, "semantic_id", None)
            item_type = getattr(item, "type", None)
        if item_type == artifact_type and item_semantic_id == semantic_id and item_id:
            return str(item_id)
    return None


def _derive_query_plan(state: dict[str, Any], observation: ToolObservation) -> dict[str, Any] | None:
    """Best-effort query plan when no explicit query plan is present.

    Prefers the plan embedded in SQL metadata, falling back to
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
        "derived_from": "db.query",
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

    # Artifact emission for execution tools
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    if (
        step_name in ("db.query", "sql.execute_readonly")
        and execution
        and execution.get("success")
        and _has_result_rows(execution)
    ):
        sql_text = str(state.get("sql") or execution.get("safe_sql") or execution.get("sql") or "").strip()
        sql_artifact = build_sql_artifact(
            sql_text,
            safety=state.get("safety"),
            execution=state.get("execution"),
            identity=identity,
        ) if sql_text else None
        source_sql_artifact_id = (
            _existing_artifact_id(state, sql_artifact.semantic_id, "sql")
            if sql_artifact is not None
            else None
        )
        if sql_artifact is not None and source_sql_artifact_id is None:
            source_sql_artifact_id = sql_artifact.id
        safety_artifact = build_safety_artifact(
            state.get("safety"),
            identity=identity,
            source_sql=sql_text,
            source_sql_artifact_id=source_sql_artifact_id,
        ) if isinstance(state.get("safety"), dict) else None
        safety_artifact_id = (
            _existing_artifact_id(state, safety_artifact.semantic_id, "safety")
            if safety_artifact is not None
            else None
        )
        if safety_artifact is not None and safety_artifact_id is None:
            safety_artifact_id = safety_artifact.id
        if sql_artifact is not None and sql_artifact.id == source_sql_artifact_id:
            artifacts.append(sql_artifact)
        if safety_artifact is not None and safety_artifact.id == safety_artifact_id:
            artifacts.append(safety_artifact)
        artifacts.append(build_result_view_artifact(
            state["execution"],
            datasource_id=state.get("datasource_id"),
            safety=state.get("safety"),
            identity=identity,
            source_sql_artifact_id=source_sql_artifact_id,
            safety_artifact_id=safety_artifact_id,
        ))

    if step_name in ("db.query", "sql.execute_readonly") and observation.output and observation.status == "success":
        payload = dict(observation.output)
        payload["produced_by_step"] = step_name
        if _has_result_rows(payload) and _has_sql_suggestion_payload(payload):
            artifacts.append(build_sql_suggestion_artifact(payload, identity=identity))

    if step_name == "chart.suggest" and state.get("chart_suggestion") and observation.status == "success":
        chart = state.get("chart_suggestion")
        if isinstance(chart, dict) and is_chartable_suggestion(chart):
            artifacts.append(build_chart_artifact(chart, safety=state.get("safety"), execution=state.get("execution"), identity=identity))

    # Bind dependencies against existing artifacts and artifacts emitted in this
    # observation so sql -> result_view -> chart stays addressable by semantic id.
    existing_artifacts = state.get("artifacts") or []
    semantic_to_id: dict[str, str] = {}
    for item in [*existing_artifacts, *artifacts]:
        if isinstance(item, dict):
            sem_id = item.get("semantic_id") or item.get("id")
            item_id = item.get("id")
        else:
            sem_id = item.semantic_id or item.id
            item_id = item.id
        if sem_id and item_id:
            semantic_to_id[sem_id] = item_id

    for art in artifacts:
        resolved: list[str] = []
        for dep in art.depends_on:
            resolved.append(semantic_to_id.get(dep, dep))
        # De-dup while preserving order
        seen_deps: set[str] = set()
        art.depends_on = [d for d in resolved if not (d in seen_deps or seen_deps.add(d))]

    return artifacts


def make_observe_working_state(state: dict[str, Any]) -> dict[str, Any]:
    working_state: dict[str, Any] = {}
    for key, value in state.items():
        if isinstance(value, list):
            working_state[key] = list(value)
        elif isinstance(value, dict):
            working_state[key] = dict(value)
        else:
            working_state[key] = value
    return working_state


def bind_observation_to_state(
    *,
    state: dict[str, Any],
    tool_name: str,
    observation: ToolObservation,
    merge_strategy: str,
) -> dict[str, Any]:
    updates = apply_tool_result_to_state(
        state=state,
        tool_name=tool_name,
        observation=observation,
        merge_strategy=merge_strategy,
    )
    updates = dict(updates)
    # observe_node emits typed AgentArtifacts; legacy reducer artifacts stay out.
    updates.pop("artifacts", None)
    return updates


def build_tool_history_entry(tool_name: str, observation: ToolObservation) -> dict[str, Any]:
    entry = {
        "name": tool_name,
        "input": _effective_tool_history_input(tool_name, observation),
        "status": observation.status,
        "error": observation.error,
    }
    if not isinstance(observation.output, dict):
        return entry

    entry["output_keys"] = list(observation.output.keys())
    if "results" in observation.output and isinstance(observation.output["results"], list):
        entry["results_count"] = len(observation.output["results"])
    if "tables" in observation.output and isinstance(observation.output["tables"], list):
        entry["results_count"] = len(observation.output["tables"])
    if "related_tables" in observation.output and isinstance(observation.output["related_tables"], list):
        entry["results_count"] = len(observation.output["related_tables"])
    if "columns" in observation.output and isinstance(observation.output["columns"], list):
        entry["columns_count"] = len(observation.output["columns"])
    if "blocked_reasons" in observation.output and isinstance(observation.output["blocked_reasons"], list):
        entry["blocked_reasons"] = observation.output["blocked_reasons"]
    if "rowCount" in observation.output:
        entry["returned_rows"] = observation.output["rowCount"]
    elif "returned_rows" in observation.output:
        entry["returned_rows"] = observation.output["returned_rows"]
    return entry


def _effective_tool_history_input(tool_name: str, observation: ToolObservation) -> dict[str, Any]:
    raw_input = dict(observation.input or {})
    if tool_name != "sql.execute_readonly":
        return raw_input

    output = observation.output or {}
    safe_sql = str(output.get("safe_sql") or "").strip() if isinstance(output, dict) else ""
    if not safe_sql:
        return raw_input

    return {
        "effective_sql_fingerprint": _arg_signature(
            "sql.execute_readonly.safe_sql",
            {"safe_sql": safe_sql},
        ),
    }


def derive_catalog_exploration_state(tool_name: str, observation: ToolObservation) -> dict[str, list[str]]:
    candidate_tables: list[str] = []
    searched_terms: list[str] = []
    exhausted_paths: list[str] = []

    output = observation.output
    if isinstance(output, dict):
        results = output.get("results") or output.get("tables") or []
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("table_name") or "").strip()
                if name:
                    candidate_tables.append(name)

        seed = output.get("seed_table") or {}
        if isinstance(seed, dict) and seed.get("table_name"):
            candidate_tables.append(str(seed["table_name"]))

        related = output.get("related_tables") or []
        if isinstance(related, list):
            for item in related:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("table_name") or "").strip()
                if name:
                    candidate_tables.append(name)

        if tool_name == "db.search" and isinstance(observation.input, dict):
            query = str(observation.input.get("query") or "").strip().lower()
            if query:
                searched_terms.append(query)

    arg_sig = _arg_signature(tool_name, observation.input or {})
    if observation.status == "failed" or _is_empty_result(tool_name, observation.output):
        exhausted_paths.append(f"{tool_name}::{arg_sig}")

    return {
        "candidate_tables": candidate_tables,
        "searched_terms": searched_terms,
        "exhausted_paths": exhausted_paths,
    }


def merge_catalog_exploration_state(
    state: dict[str, Any],
    catalog_updates: dict[str, list[str]],
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    candidate_tables_new = catalog_updates.get("candidate_tables") or []
    searched_terms_new = catalog_updates.get("searched_terms") or []
    exhausted_paths_new = catalog_updates.get("exhausted_paths") or []

    if candidate_tables_new:
        existing = list(state.get("candidate_tables") or [])
        seen = set(existing)
        for name in candidate_tables_new:
            if name not in seen:
                existing.append(name)
                seen.add(name)
        merged["candidate_tables"] = existing

    if searched_terms_new:
        existing = [str(term).lower() for term in (state.get("searched_terms") or [])]
        for term in searched_terms_new:
            if term not in existing:
                existing.append(term)
        merged["searched_terms"] = existing

    if exhausted_paths_new:
        existing = list(state.get("exhausted_paths") or [])
        seen = set(existing)
        for path in exhausted_paths_new:
            if path not in seen:
                existing.append(path)
                seen.add(path)
        merged["exhausted_paths"] = existing

    return merged


def rebuild_context_pack(state: dict[str, Any], state_updates: dict[str, Any]) -> dict[str, Any]:
    from engine.agent.context_pack import build_context_pack

    merged_state = dict(state)
    merged_state.update(state_updates)
    return {"context_pack": build_context_pack(merged_state).model_dump(mode="json")}


def observe_tools(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    ctx = graph_context(config)
    run_id = state.get("run_id") or ""

    last_tool_results = state.get("last_tool_results") or []

    state_updates: dict[str, Any] = {}
    # Shallow-copy top-level keys to avoid RecursionError from deepcopy of
    # deeply nested LangChain messages / artifacts.
    temp_state = make_observe_working_state(state)

    new_artifacts_dicts = []

    tool_history_entries = []
    catalog_updates: dict[str, list[str]] = {
        "candidate_tables": [],
        "searched_terms": [],
        "exhausted_paths": [],
    }

    for result_dict in last_tool_results:
        try:
            obs = ToolObservation.model_validate(result_dict)
            step_name = obs.name
            tool_name = _tool_name_from_step(step_name)
            tool = ctx.registry.get(tool_name)
            merge_strategy = tool.spec.state.merge_strategy if tool is not None else "reuse"

            databinding_updates = bind_observation_to_state(
                state=temp_state,
                tool_name=tool_name,
                observation=obs,
                merge_strategy=merge_strategy,
            )

            temp_state.update(databinding_updates)
            
            # Merge updates (accumulating lists)
            for k, v in databinding_updates.items():
                if k in {"tool_results", "trace_events"}:
                    state_updates.setdefault(k, []).extend(v)
                else:
                    state_updates[k] = v

            tool_history_entries.append(build_tool_history_entry(tool_name, obs))

            derived_catalog = derive_catalog_exploration_state(tool_name, obs)
            for key, values in derived_catalog.items():
                catalog_updates[key].extend(values)

            artifacts = emit_artifacts_from_observation(step_name, obs, temp_state, run_id)
            if artifacts:
                for art in artifacts:
                    art_dict = art.model_dump(mode="json")
                    new_artifacts_dicts.append(art_dict)
        except Exception as exc:
            logger.warning("Failed to process tool observation: %s (payload: %s)", exc, result_dict, exc_info=True)
            continue

    if tool_history_entries:
        state_updates["tool_call_history"] = tool_history_entries

    state_updates.update(merge_catalog_exploration_state(temp_state, catalog_updates))

    if new_artifacts_dicts:
        state_updates["artifacts"] = new_artifacts_dicts

    # ---- Rebuild ContextPack (Agent v2) ------------------------------------
    try:
        state_updates.update(rebuild_context_pack(state, state_updates))
    except Exception as exc:
        logger.warning("Failed to build ContextPack: %s", exc)

    return state_updates
