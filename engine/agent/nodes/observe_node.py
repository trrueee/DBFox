from __future__ import annotations

import logging
from typing import Any
from langchain_core.runnables import RunnableConfig

from engine.agent_core.types import ToolObservation
from engine.agent_core.databinding import apply_tool_result_to_state
from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent_core.artifacts import (
    AgentArtifactIdentity,
    build_chart_artifact,
    build_sql_suggestion_artifact,
    build_profile_artifact,
    build_query_plan_artifact,
    build_safety_artifact,
    build_sql_artifact,
    build_table_artifact,
)
from engine.agent_core.types import ResultProfile

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


from engine.agent.tools.tool_aliases import STEP_NAME_TO_INTERNAL


def _tool_name_from_step(step_name: str) -> str:
    return STEP_NAME_TO_INTERNAL.get(step_name, step_name)


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
    if step_name in ("db.query", "sql.execute_readonly") and state.get("execution") and state.get("execution", {}).get("success"):
        artifacts.append(build_table_artifact(state["execution"], safety=state.get("safety"), identity=identity))

    if step_name in ("db.query", "sql.execute_readonly") and observation.output and observation.status == "success":
        payload = dict(observation.output)
        payload["produced_by_step"] = step_name
        artifacts.append(build_sql_suggestion_artifact(payload, identity=identity))

    if step_name == "result.profile" and state.get("result_profile") and observation.status == "success":
        profile_raw = state.get("result_profile")
        if isinstance(profile_raw, dict):
            try:
                profile_obj = ResultProfile.model_validate(profile_raw)
            except Exception:
                profile_obj = None
        elif isinstance(profile_raw, ResultProfile):
            profile_obj = profile_raw
        else:
            profile_obj = None
        if profile_obj is not None:
            artifacts.append(build_profile_artifact(
                profile_obj,
                execution=state.get("execution"),
                safety=state.get("safety"),
                identity=identity,
            ))

    if step_name == "chart.suggest" and state.get("chart_suggestion") and observation.status == "success":
        chart = state.get("chart_suggestion")
        if isinstance(chart, dict) and chart.get("type") and chart.get("type") != "table":
            artifacts.append(build_chart_artifact(chart, safety=state.get("safety"), execution=state.get("execution"), identity=identity))

    # Bind dependencies. result_table is now keyed per-query (result_table_{hash}),
    # so a bare "result_table" dep must resolve to the most recent table artifact.
    existing_artifacts = state.get("artifacts") or []
    semantic_to_id: dict[str, str] = {}
    latest_table_id: str | None = None
    for item in existing_artifacts:
        if isinstance(item, dict):
            sem_id = item.get("semantic_id") or item.get("id")
            item_id = item.get("id")
            item_type = item.get("type")
        else:
            sem_id = item.semantic_id or item.id
            item_id = item.id
            item_type = item.type
        if sem_id and item_id:
            semantic_to_id[sem_id] = item_id
        if item_type == "table" and item_id:
            latest_table_id = item_id

    for art in artifacts:
        resolved: list[str] = []
        for dep in art.depends_on:
            if dep == "result_table":
                resolved.append(semantic_to_id.get(dep) or latest_table_id or dep)
            else:
                resolved.append(semantic_to_id.get(dep, dep))
        # De-dup while preserving order
        seen_deps: set[str] = set()
        art.depends_on = [d for d in resolved if not (d in seen_deps or seen_deps.add(d))]

    return artifacts


def observe_tools(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    ctx = graph_context(config)
    run_id = state.get("run_id") or ""

    last_tool_results = state.get("last_tool_results") or []

    state_updates: dict[str, Any] = {}
    # Shallow-copy each top-level key individually to avoid RecursionError
    # from deepcopy of deeply nested LangChain messages / artifacts.
    temp_state: dict[str, Any] = {}
    for k, v in state.items():
        if isinstance(v, list):
            temp_state[k] = list(v)
        elif isinstance(v, dict):
            temp_state[k] = dict(v)
        else:
            temp_state[k] = v

    new_artifacts_dicts = []

    tool_history_entries = []
    candidate_tables_new: list[str] = []
    searched_terms_new: list[str] = []
    exhausted_paths_new: list[str] = []

    for result_dict in last_tool_results:
        try:
            obs = ToolObservation.model_validate(result_dict)
            step_name = obs.name
            tool_name = _tool_name_from_step(step_name)
            tool = ctx.registry.get(tool_name)
            merge_strategy = tool.spec.state.merge_strategy if tool is not None else "reuse"

            databinding_updates = apply_tool_result_to_state(
                state=temp_state,
                tool_name=tool_name,
                observation=obs,
                merge_strategy=merge_strategy,
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

            history_entry = {
                "name": tool_name,
                "input": obs.input or {},
                "status": obs.status,
                "error": obs.error,
            }
            if isinstance(obs.output, dict):
                history_entry["output_keys"] = list(obs.output.keys())
                if "results" in obs.output and isinstance(obs.output["results"], list):
                    history_entry["results_count"] = len(obs.output["results"])
                if "tables" in obs.output and isinstance(obs.output["tables"], list):
                    history_entry["results_count"] = len(obs.output["tables"])
                if "related_tables" in obs.output and isinstance(obs.output["related_tables"], list):
                    history_entry["results_count"] = len(obs.output["related_tables"])
                if "columns" in obs.output and isinstance(obs.output["columns"], list):
                    history_entry["columns_count"] = len(obs.output["columns"])
                if "blocked_reasons" in obs.output and isinstance(obs.output["blocked_reasons"], list):
                    history_entry["blocked_reasons"] = obs.output["blocked_reasons"]
                if "rowCount" in obs.output:
                    history_entry["returned_rows"] = obs.output["rowCount"]
                elif "returned_rows" in obs.output:
                    history_entry["returned_rows"] = obs.output["returned_rows"]
            
            tool_history_entries.append(history_entry)

            # ── Large Catalog Exploration: track candidate_tables ──────────
            if isinstance(obs.output, dict):
                # db.search / schema.list_tables_page → collect table names
                results = obs.output.get("results") or obs.output.get("tables") or []
                if isinstance(results, list):
                    for item in results:
                        name = (item.get("name") or item.get("table_name") or "").strip()
                        if name:
                            candidate_tables_new.append(name)
                # schema.expand_related_tables → seed + related
                seed = obs.output.get("seed_table") or {}
                if isinstance(seed, dict) and seed.get("table_name"):
                    candidate_tables_new.append(str(seed["table_name"]))
                related = obs.output.get("related_tables") or []
                if isinstance(related, list):
                    for r in related:
                        n = (r.get("table_name") or "").strip()
                        if n:
                            candidate_tables_new.append(n)

                # Track searched terms (db.search)
                if tool_name == "db.search" and isinstance(obs.input, dict):
                    q = str(obs.input.get("query") or "").strip().lower()
                    if q:
                        searched_terms_new.append(q)

            # Track exhausted paths for empty/failed results.
            # Use the same SHA-based signature as check_loop_prevention so the
            # exhausted_paths pre-check in fast_path can match.
            from engine.agent.progress.fast_path import _arg_signature
            arg_sig = _arg_signature(tool_name, obs.input or {})

            if obs.status == "failed" or _is_empty_result(tool_name, obs.output):
                exhausted_paths_new.append(f"{tool_name}::{arg_sig}")

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

    # ── Large Catalog Exploration: dedup and merge ────────────────────────
    if candidate_tables_new:
        existing_ct = list(temp_state.get("candidate_tables") or [])
        seen_ct = set(existing_ct)
        for n in candidate_tables_new:
            if n not in seen_ct:
                existing_ct.append(n)
                seen_ct.add(n)
        state_updates["candidate_tables"] = existing_ct

    if searched_terms_new:
        existing_st = [s.lower() for s in (temp_state.get("searched_terms") or [])]
        for t in searched_terms_new:
            if t not in existing_st:
                existing_st.append(t)
        state_updates["searched_terms"] = existing_st

    if exhausted_paths_new:
        existing_ep = list(temp_state.get("exhausted_paths") or [])
        seen_ep = set(existing_ep)
        for p in exhausted_paths_new:
            if p not in seen_ep:
                existing_ep.append(p)
                seen_ep.add(p)
        state_updates["exhausted_paths"] = existing_ep

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
