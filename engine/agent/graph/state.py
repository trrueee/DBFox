from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages

# Reducer for append-only lists (artifacts, trace_events, runtime_events).
# messages uses its own add_messages reducer from LangGraph.


def _add_list(left: list[Any], right: list[Any]) -> list[Any]:
    if right and isinstance(right[0], dict) and right[0].get("__clear__"):
        return right[1:]
    return left + right


AgentStatus = Literal[
    "running",
    "waiting_approval",
    "waiting_user",
    "completed",
    "failed",
]


class DataBoxAgentState(TypedDict, total=False):
    # ---- Core LangGraph agent-loop state ----------------------------------
    messages: Annotated[list[Any], add_messages]

    # ---- Run identity -----------------------------------------------------
    run_id: str
    thread_id: str
    session_id: str
    datasource_id: str
    user_id: str | None
    project_id: str | None
    parent_run_id: str | None

    # ---- Runtime flags ----------------------------------------------------
    execute: bool
    max_steps: int
    step_count: int
    status: AgentStatus

    # ---- Planner output ----------------------------------------------------
    plan_directive: dict[str, Any] | None
    execution_mode: str
    allowed_tool_groups: list[str]
    selected_skill_ids: list[str]

    # ---- Environment / Semantic layers -------------------------------------
    environment_profile: dict[str, Any] | None
    database_map: dict[str, Any] | None
    semantic_resolution: dict[str, Any] | None
    db_search_results: dict[str, Any] | None
    db_inspection: dict[str, Any] | None
    db_preview: dict[str, Any] | None

    # ---- Request-level context --------------------------------------------
    workspace_context: dict[str, Any] | None
    follow_up_context: dict[str, Any] | None

    # ---- DataBox factual state (written by observe_node) ------------------
    schema_context: dict[str, Any] | None
    schema_metadata: dict[str, Any] | None
    query_plan: dict[str, Any] | None
    sql_candidate: dict[str, Any] | None
    sql: str | None
    safety: dict[str, Any] | None
    execution: dict[str, Any] | None
    result_profile: dict[str, Any] | None
    chart_suggestion: dict[str, Any] | None
    suggestions: list[dict[str, Any]]
    answer: dict[str, Any] | None
    final_answer: dict[str, Any] | None

    # ---- Tool-call / policy routing ---------------------------------------
    pending_tool_calls: list[dict[str, Any]]
    allowed_tool_calls: list[dict[str, Any]]
    blocked_tool_calls: list[dict[str, Any]]
    last_tool_results: list[dict[str, Any]]
    last_observation: dict[str, Any] | None
    last_tool_name: str | None
    last_tool_metadata: dict[str, Any] | None

    # ---- ContextPack (Agent v2 structured context) -------------------------
    context_pack: dict[str, Any] | None

    # ---- Progress Judge output ---------------------------------------------
    progress_decision: dict[str, Any] | None

    # ---- Anti-loop ---------------------------------------------------------
    replan_count: int
    consecutive_blocks: int

    # ---- Human-in-the-loop approval ---------------------------------------
    pending_approval: dict[str, Any] | None
    approval_result: dict[str, Any] | None

    # ---- Append-only collections ------------------------------------------
    artifacts: Annotated[list[dict[str, Any]], _add_list]
    trace_events: Annotated[list[dict[str, Any]], _add_list]
    runtime_events: Annotated[list[dict[str, Any]], _add_list]
    plan_events: Annotated[list[dict[str, Any]], _add_list]

    # ---- Errors -----------------------------------------------------------
    error: str | None
    last_error_telemetry: dict[str, Any] | None

    # ---- Revision tracking -------------------------------------------------
    revision_attempted: bool
    revision_count: int
    repair_mode: bool
    repair_stats: dict[str, Any] | None
    repair_trace: Annotated[list[dict[str, Any]], _add_list]

    # ---- Follow-up --------------------------------------------------------
    followup_context: dict[str, Any] | None
    chart_request: bool

    # ---- Visible plan (UI-only, not a scheduler) --------------------------
    agent_intent: dict[str, Any] | None
    agent_context: dict[str, Any] | None
    visible_plan: dict[str, Any] | None
    plan: dict[str, Any] | None
