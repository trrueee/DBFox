from __future__ import annotations

import logging
from typing import Any, cast

from sqlalchemy.orm import Session

from engine.agent.app.memory_projection import AgentMemoryProjectionCoordinator, restore_session_memory
from engine.agent.app.persistence import pending_approval_from_workspace
from engine.agent.graph.state import DBFoxAgentState, sync_state_namespaces
from engine.agent_core.types import AgentRunRequest
from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception

logger = logging.getLogger("dbfox.dbfox_agent.context_builder")

# Full set of safe tool groups available to the model on every run.
# The policy gate and execution_mode control what actually executes.
FULL_SAFE_TOOL_GROUPS = [
    "environment", "schema", "db",
    "result", "chart", "sql",
]


class AgentContextBuilder:
    """Build the graph input state and contextual payloads for an agent run."""

    def __init__(
        self,
        db: Session,
        memory_projection: AgentMemoryProjectionCoordinator,
    ):
        self.db = db
        self.memory_projection = memory_projection

    def build_initial_state(
        self,
        req: AgentRunRequest,
        *,
        run_id: str,
        session_id: str,
    ) -> DBFoxAgentState:
        pending_approval = pending_approval_from_workspace(self.db, req)
        context_bundle = _build_context_bundle(self.db, req)
        context_summary = context_bundle.get("context_summary")
        environment_profile, database_map = _environment_context_payload(self.db, req.datasource_id)
        if req.execution_mode:
            execution_mode = req.execution_mode
        else:
            execution_mode = "user_requested_read" if req.execute else "suggest_only"
        clear_marker: Any = {"__clear__": True}
        state = DBFoxAgentState(
            run_id=run_id,
            thread_id=session_id,
            session_id=session_id,
            datasource_id=req.datasource_id,
            question=req.question,
            execute=req.execute,
            status="running",
            messages=[],
            workspace_context=_workspace_context_payload(req, context_bundle),
            follow_up_context=req.follow_up_context.model_dump(mode="json") if req.follow_up_context else None,
            context_summary=context_summary if isinstance(context_summary, str) else None,
            max_steps=req.max_steps,
            step_count=0,
            # ---- Progress Judge state ----
            execution_mode=execution_mode,
            allowed_tool_groups=FULL_SAFE_TOOL_GROUPS,
            progress_decision=None,
            replan_count=0,
            consecutive_blocks=0,
            # ---- Environment / Semantic layers ----
            environment_profile=environment_profile,
            database_map=database_map,
            semantic_resolution=_semantic_resolution_payload(context_bundle),
            db_search_results=None,
            db_inspection=None,
            db_preview=None,
            # ---- Large Catalog Exploration ----
            candidate_tables=[],
            searched_terms=[clear_marker],
            exhausted_paths=[clear_marker],
            # ---- Multi-query Analysis Units ----
            analysis_units=[{"__clear__": True}],
            current_analysis_unit_id=None,
            # ---- Tool-call / policy routing ----
            pending_tool_calls=[],
            allowed_tool_calls=[],
            blocked_tool_calls=[],
            last_tool_results=[],
            artifacts=[{"__clear__": True}],
            trace_events=[{"__clear__": True}],
            runtime_events=[{"__clear__": True}],
            plan_events=[{"__clear__": True}],
            suggestions=[{"__clear__": True}],
            tool_call_history=[{"__clear__": True}],
            error=None,
            pending_approval=pending_approval,
            parent_run_id=req.parent_run_id,
            sql=None,
            safety=None,
            execution=None,
            schema_context=_schema_context_payload(context_bundle),
            query_plan=None,
            chart_suggestion=None,
            answer=None,
            final_answer=None,
            revision_attempted=False,
            revision_count=0,
            repair_mode=False,
            repair_stats=None,
            reusable_sql_candidates=self.memory_projection.list_reusable_sqls(req.datasource_id),
        )
        restore_session_memory(
            cast(dict[str, Any], state),
            self.memory_projection.load_session_memory(session_id),
            datasource_id=req.datasource_id,
        )
        sync_state_namespaces(cast(dict[str, Any], state))
        return state


def _build_context_bundle(db: Session, req: AgentRunRequest) -> dict[str, Any]:
    try:
        from engine.agent_core.workspace_context import build_agent_context_bundle

        bundle = build_agent_context_bundle(db, req)
    except Exception as exc:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_CONTEXT_BUILD_WORKSPACE,
            exc=exc,
            level="warning",
        )
        return {}
    return bundle if isinstance(bundle, dict) else {}


def _workspace_context_payload(
    req: AgentRunRequest,
    context_bundle: dict[str, Any],
) -> dict[str, Any] | None:
    workspace = context_bundle.get("workspace")
    if isinstance(workspace, dict):
        return workspace
    return req.workspace_context.model_dump(mode="json") if req.workspace_context else None


def _schema_context_payload(context_bundle: dict[str, Any]) -> dict[str, Any] | None:
    schema_linking = context_bundle.get("schema_linking")
    return schema_linking if isinstance(schema_linking, dict) else None


def _semantic_resolution_payload(context_bundle: dict[str, Any]) -> dict[str, Any] | None:
    semantic_context = context_bundle.get("semantic_context")
    schema_linking = context_bundle.get("schema_linking")
    payload: dict[str, Any] = {}
    if isinstance(semantic_context, dict):
        payload.update(semantic_context)
    if isinstance(schema_linking, dict):
        for key in (
            "semantic_aliases_used",
            "schema_linking_reasons",
            "selected_tables",
            "selected_columns",
        ):
            value = schema_linking.get(key)
            if value:
                payload[key] = value
    return payload or None


def _environment_context_payload(
    db: Session,
    datasource_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        from engine.environment.tools import environment_get_profile

        profile = environment_get_profile(db, datasource_id)
    except Exception as exc:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_CONTEXT_BUILD_ENVIRONMENT,
            exc=exc,
            level="warning",
        )
        return None, None

    if not isinstance(profile, dict):
        return None, None
    database_map = profile.get("database_map")
    return profile, database_map if isinstance(database_map, dict) else None
