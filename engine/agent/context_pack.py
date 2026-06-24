"""ContextPack — structured, multi-view context container for DBFox Agent v2.

Instead of each node (Planner, Model, Progress Judge) independently building
context from raw state, the ContextPack is assembled once after each observe
cycle and rendered into node-specific views.

Structure:
    ContextPack
    ├─ workspace     — current datasource / table / SQL / result / error
    ├─ environment    — env tier / dialect / catalog / warnings
    ├─ schema_context — selected tables / columns / DDL
    ├─ semantic       — business terms / metrics / dimensions / join paths
    ├─ query_plan     — structured query plan artifact
    ├─ sql            — current SQL candidate
    ├─ safety         — TrustGate / guardrail result
    ├─ execution      — query execution result
    ├─ result         — analysis units summary / chart type
    ├─ memory         — relevant memories (auto-injected)
    ├─ run_state      — step count / retry history / error
    └─ skill          — active skill guidance
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from engine.agent_core.chart_builder import is_chartable_suggestion


# ── Section models ─────────────────────────────────────────────────────────────


class WorkspaceSection(BaseModel):
    datasource_id: str = ""
    active_sql: str | None = None
    active_table: str | None = None
    selected_tables: list[str] = Field(default_factory=list)
    selected_columns: list[str] = Field(default_factory=list)
    selected_artifact_id: str | None = None
    open_tab_titles: list[str] = Field(default_factory=list)
    has_result: bool = False
    result_preview_rows: int = 0
    error_summary: str | None = None


class EnvironmentSection(BaseModel):
    env_tier: str = "unknown"
    dialect: str = "unknown"
    catalog_status: str = "unknown"
    table_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SchemaSection(BaseModel):
    selected_tables: list[str] = Field(default_factory=list)
    candidate_columns: list[str] = Field(default_factory=list)
    ddl_snippet: str | None = None
    ddl_size: int = 0


class SqlSection(BaseModel):
    sql: str | None = None
    sql_size: int = 0


class SafetySection(BaseModel):
    can_execute: bool = False
    requires_confirmation: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    passed: bool = False


class ExecutionSection(BaseModel):
    success: bool = False
    row_count: int = 0
    columns: list[str] = Field(default_factory=list)
    error: str | None = None
    truncated: bool = False


class ResultSection(BaseModel):
    query_count: int = 0
    total_rows: int = 0
    non_empty_queries: int = 0
    chart_type: str | None = None


class MemorySection(BaseModel):
    planner_hints: str = ""
    recovery_hints: str = ""


class RunStateSection(BaseModel):
    step_count: int = 0
    max_steps: int = 20
    retry_budget: int = 0
    replan_count: int = 0
    revision_count: int = 0
    status: str = "running"
    error: str | None = None


class SkillSection(BaseModel):
    selected_skill_ids: list[str] = Field(default_factory=list)
    skill_summary: str = ""


class IntentSection(BaseModel):
    original_question: str = ""
    is_follow_up: bool = False
    parent_run_id: str | None = None
    task_type: str = ""
    execution_mode: str = ""
    success_criteria: list[str] = Field(default_factory=list)


class RecentActivitySection(BaseModel):
    artifact_summaries: list[str] = Field(default_factory=list)
    follow_up_summary: str | None = None
    recent_sql_snippets: list[str] = Field(default_factory=list)


class ConstraintsSection(BaseModel):
    execute_allowed: bool = True
    max_steps: int = 20
    requires_approval: bool = False
    policy_blocked_tools: int = 0


# ── ContextPack ────────────────────────────────────────────────────────────────


class ContextPack(BaseModel):
    """Structured context assembled after each observe cycle.

    Consumed by Planner, Model, and Progress Judge — each via its own
    renderer that selects and formats the relevant sections.
    """

    workspace: WorkspaceSection = Field(default_factory=WorkspaceSection)
    environment: EnvironmentSection = Field(default_factory=EnvironmentSection)
    schema_context: SchemaSection = Field(
        default_factory=SchemaSection,
        validation_alias=AliasChoices("schema_context", "schema"),
    )
    sql: SqlSection = Field(default_factory=SqlSection)
    safety: SafetySection = Field(default_factory=SafetySection)
    execution: ExecutionSection = Field(default_factory=ExecutionSection)
    result: ResultSection = Field(default_factory=ResultSection)
    memory: MemorySection = Field(default_factory=MemorySection)
    run_state: RunStateSection = Field(default_factory=RunStateSection)
    skill: SkillSection = Field(default_factory=SkillSection)
    intent: IntentSection = Field(default_factory=IntentSection)
    recent_activity: RecentActivitySection = Field(default_factory=RecentActivitySection)
    constraints: ConstraintsSection = Field(default_factory=ConstraintsSection)
    ui_summary: str = ""

    @property
    def has_data(self) -> bool:
        """True if the pack contains any non-trivial context beyond defaults."""
        return bool(
            self.schema_context.selected_tables
            or self.sql.sql
            or self.execution.success
            or self.result.total_rows > 0
        )

    @property
    def is_failing(self) -> bool:
        """True if the run is in a failure state."""
        return bool(
            self.run_state.error
            or (self.execution.error is not None)
            or self.run_state.status in ("failed", "blocked")
        )


# ── Builder ────────────────────────────────────────────────────────────────────
#
# Each ``_build_*_section`` function extracts a single section from raw agent
# state.  ``build_context_pack`` orchestrates them — it does zero inline parsing.


def build_context_pack(state: dict[str, Any]) -> ContextPack:
    """Build a ContextPack from raw agent state.

    Called after each observe cycle.  All sections are populated from the
    current state snapshot — no side effects.  Section builders are
    independently testable.
    """
    pack = ContextPack(
        workspace=_build_workspace_section(state),
        environment=_build_environment_section(state),
        schema_context=_build_schema_section(state),
        sql=_build_sql_section(state),
        safety=_build_safety_section(state),
        execution=_build_execution_section(state),
        result=_build_result_section(state),
        memory=_build_memory_section(),
        run_state=_build_runstate_section(state),
        skill=_build_skill_section(state),
        intent=_build_intent_section(state),
        recent_activity=_build_recent_activity_section(state),
        constraints=_build_constraints_section(state),
    )
    pack.ui_summary = render_ui_summary(pack)
    return pack


# ── Section builders ────────────────────────────────────────────────────────────


def _build_workspace_section(state: dict[str, Any]) -> WorkspaceSection:
    ws_raw = state.get("workspace_context") or {}
    if not isinstance(ws_raw, dict):
        return WorkspaceSection(
            datasource_id=str(state.get("datasource_id") or ""),
            error_summary=_str_or_none(state.get("error")),
        )

    ws_tables = _normalize_str_list(
        ws_raw.get("selected_table_names") or ws_raw.get("selected_tables") or []
    )
    ws_columns = _normalize_str_list(ws_raw.get("selected_column_refs") or [])
    open_tabs = ws_raw.get("open_sql_tabs") or []
    tab_titles = [
        str(t.get("title") or t.get("id") or "")
        for t in open_tabs[:6]
        if isinstance(t, dict) and (t.get("title") or t.get("id"))
    ]
    preview = ws_raw.get("last_query_result_preview") or {}
    preview_rows = int(preview.get("row_count") or preview.get("rows") or 0) if isinstance(preview, dict) else 0
    active_table = ws_raw.get("active_table")
    if not active_table and ws_tables:
        active_table = ws_tables[0]

    return WorkspaceSection(
        datasource_id=str(state.get("datasource_id") or ws_raw.get("datasource_id") or ""),
        active_sql=_str_or_none(ws_raw.get("selected_sql") or ws_raw.get("active_sql")),
        active_table=_str_or_none(active_table),
        selected_tables=ws_tables[:10],
        selected_columns=ws_columns[:20],
        selected_artifact_id=_str_or_none(ws_raw.get("selected_artifact_id")),
        open_tab_titles=tab_titles,
        has_result=bool(ws_raw.get("has_result") or preview_rows > 0),
        result_preview_rows=preview_rows,
        error_summary=_str_or_none(ws_raw.get("last_error") or state.get("error")),
    )


def _build_environment_section(state: dict[str, Any]) -> EnvironmentSection:
    env_raw = state.get("environment_profile") or {}
    env_warnings: list[str] = [str(w) for w in (env_raw.get("warnings") or [])]
    return EnvironmentSection(
        env_tier=str(env_raw.get("env") or env_raw.get("env_tier") or "unknown"),
        dialect=str(env_raw.get("dialect") or "unknown"),
        catalog_status=str(env_raw.get("catalog_status") or "unknown"),
        table_count=int(env_raw.get("table_count") or 0),
        warnings=env_warnings[:5],
    )


def _build_schema_section(state: dict[str, Any]) -> SchemaSection:
    schema_raw = state.get("schema_context") or {}
    selected_tables: list[str] = []
    candidate_columns: list[str] = []
    ddl: str | None = None
    ddl_size = 0
    if isinstance(schema_raw, dict):
        selected_tables = [str(t) for t in (schema_raw.get("selected_tables") or [])]
        candidate_columns = _normalize_str_list(
            schema_raw.get("candidate_columns") or schema_raw.get("selected_columns") or []
        )[:30]
        ddl = _str_or_none(schema_raw.get("schema_context"))
        ddl_size = int(schema_raw.get("schema_context_size") or 0)
    return SchemaSection(
        selected_tables=selected_tables,
        candidate_columns=candidate_columns,
        ddl_snippet=ddl,
        ddl_size=ddl_size,
    )


def _build_sql_section(state: dict[str, Any]) -> SqlSection:
    sql_raw = state.get("sql")
    sql_str: str | None = None
    if isinstance(sql_raw, str):
        sql_str = sql_raw
    elif isinstance(sql_raw, dict):
        sql_str = sql_raw.get("sql") or str(sql_raw)
    return SqlSection(sql=sql_str, sql_size=len(sql_str) if sql_str else 0)


def _build_safety_section(state: dict[str, Any]) -> SafetySection:
    safety_raw = state.get("safety") or {}
    return SafetySection(
        can_execute=bool(safety_raw.get("can_execute")),
        requires_confirmation=bool(safety_raw.get("requires_confirmation")),
        blocked_reasons=_normalize_str_list(safety_raw.get("blocked_reasons") or []),
        passed=bool(safety_raw.get("passed")),
    )


def _build_execution_section(state: dict[str, Any]) -> ExecutionSection:
    exec_raw = state.get("execution") or {}
    return ExecutionSection(
        success=bool(exec_raw.get("success")),
        row_count=int(exec_raw.get("rowCount") or 0),
        columns=_normalize_str_list(exec_raw.get("columns") or []),
        error=_str_or_none(exec_raw.get("error")),
        truncated=bool(exec_raw.get("truncated")),
    )


def _build_result_section(state: dict[str, Any]) -> ResultSection:
    units = state.get("analysis_units") or []
    non_empty = [u for u in units if not u.get("is_empty")]
    total_rows = sum(
        int((u.get("execution") or {}).get("rowCount", 0)) for u in non_empty
    )
    chart_suggestion = state.get("chart_suggestion")
    chart_type = None
    if isinstance(chart_suggestion, dict) and is_chartable_suggestion(chart_suggestion):
        chart_type = _str_or_none(chart_suggestion.get("chart_type") or chart_suggestion.get("type"))
    return ResultSection(
        query_count=len(units),
        total_rows=total_rows,
        non_empty_queries=len(non_empty),
        chart_type=chart_type,
    )


def _build_memory_section() -> MemorySection:
    return MemorySection()


def _build_runstate_section(state: dict[str, Any]) -> RunStateSection:
    return RunStateSection(
        step_count=int(state.get("step_count") or 0),
        max_steps=int(state.get("max_steps") or 20),
        retry_budget=int((state.get("progress_decision") or {}).get("retry_budget") or 0),
        replan_count=int(state.get("replan_count") or 0),
        revision_count=int(state.get("revision_count") or 0),
        status=str(state.get("status") or "running"),
        error=_str_or_none(state.get("error")),
    )


def _build_skill_section(state: dict[str, Any]) -> SkillSection:
    plan = state.get("plan_directive") or {}
    return SkillSection(
        selected_skill_ids=state.get("selected_skill_ids") or [],
        skill_summary=plan.get("reasoning_summary", ""),
    )


def _build_intent_section(state: dict[str, Any]) -> IntentSection:
    plan = state.get("plan_directive") or {}
    follow_up = state.get("follow_up_context") or {}
    return IntentSection(
        original_question=_first_user_message(state),
        is_follow_up=bool(state.get("parent_run_id") or follow_up),
        parent_run_id=_str_or_none(state.get("parent_run_id")),
        task_type=str(plan.get("task_type") or ""),
        execution_mode=str(state.get("execution_mode") or plan.get("execution_mode") or ""),
        success_criteria=_normalize_str_list(plan.get("success_criteria") or [])[:5],
    )


def _build_recent_activity_section(state: dict[str, Any]) -> RecentActivitySection:
    ws_raw = state.get("workspace_context") or {}
    ws_ctx = ws_raw if isinstance(ws_raw, dict) else {}
    workspace = _build_workspace_section(state)

    artifact_summaries: list[str] = []
    for art in (state.get("artifacts") or [])[-8:]:
        if isinstance(art, dict):
            art_type = str(art.get("type") or "artifact")
            title = str(art.get("title") or art.get("semantic_id") or art_type)
            artifact_summaries.append(f"{art_type}:{title}")

    recent_sql: list[str] = []
    if workspace.active_sql:
        recent_sql.append(workspace.active_sql[:200])
    for tab_title, tab_sql in zip(workspace.open_tab_titles, _open_tab_sql(ws_ctx)):
        if tab_sql:
            recent_sql.append(f"{tab_title}: {tab_sql[:120]}")

    follow_up_raw = state.get("follow_up_context") or {}
    follow_up_summary = None
    if isinstance(follow_up_raw, dict) and follow_up_raw.get("previous_question"):
        follow_up_summary = f"Follow-up to: {follow_up_raw.get('previous_question', '')[:120]}"

    return RecentActivitySection(
        artifact_summaries=artifact_summaries,
        follow_up_summary=follow_up_summary,
        recent_sql_snippets=recent_sql[:4],
    )


def _build_constraints_section(state: dict[str, Any]) -> ConstraintsSection:
    blocked = state.get("blocked_tool_calls") or []
    return ConstraintsSection(
        execute_allowed=bool(state.get("execute", True)),
        max_steps=int(state.get("max_steps") or 20),
        requires_approval=bool((state.get("safety") or {}).get("requires_confirmation")),
        policy_blocked_tools=len(blocked) if isinstance(blocked, list) else 0,
    )


# ── Renderers (node-specific views) ────────────────────────────────────────────


def render_for_planner(pack: ContextPack) -> str:
    """Planner view: compact, focused on environment + memory + run state."""
    parts: list[str] = []

    if pack.environment.dialect != "unknown":
        parts.append(
            f"Environment: {pack.environment.env_tier}/{pack.environment.dialect}, "
            f"catalog={pack.environment.catalog_status}, "
            f"tables={pack.environment.table_count}"
        )

    if pack.memory.planner_hints:
        parts.append(pack.memory.planner_hints)

    if pack.workspace.selected_tables:
        parts.append(f"Workspace tables: {', '.join(pack.workspace.selected_tables[:6])}")
    if pack.schema_context.selected_tables:
        parts.append(f"Active tables: {', '.join(pack.schema_context.selected_tables[:10])}")
    if pack.intent.original_question:
        parts.append(f"Goal: {pack.intent.original_question[:160]}")

    if pack.skill.selected_skill_ids:
        parts.append(f"Active skills: {', '.join(pack.skill.selected_skill_ids)}")

    if pack.run_state.error:
        parts.append(f"Last error: {pack.run_state.error[:200]}")

    return "\n".join(parts)


def render_for_model(pack: ContextPack) -> str:
    """Model view: full context with all factual state for ReAct reasoning."""
    parts = ["### DBFox Current State"]

    if pack.intent.original_question:
        parts.append(f"- **User Goal**: {pack.intent.original_question[:500]}")
    if pack.intent.is_follow_up and pack.recent_activity.follow_up_summary:
        parts.append(f"- **Follow-up**: {pack.recent_activity.follow_up_summary}")

    # Workspace anchors
    if pack.workspace.selected_tables or pack.workspace.active_table:
        tables = pack.workspace.selected_tables or ([pack.workspace.active_table] if pack.workspace.active_table else [])
        parts.append(f"- **Workspace Tables**: {', '.join(t for t in tables if t)}")
    if pack.workspace.selected_columns:
        parts.append(f"- **Selected Columns**: {', '.join(pack.workspace.selected_columns[:12])}")
    if pack.workspace.active_sql:
        parts.append(f"- **Editor SQL**:\n```sql\n{pack.workspace.active_sql[:1500]}\n```")
    if pack.workspace.open_tab_titles:
        parts.append(f"- **Open Tabs**: {', '.join(pack.workspace.open_tab_titles[:6])}")

    # Environment
    parts.append(
        f"- **Environment**: {pack.environment.env_tier}, "
        f"dialect={pack.environment.dialect}, "
        f"catalog={pack.environment.catalog_status}, "
        f"tables={pack.environment.table_count}"
    )
    if pack.environment.warnings:
        parts.append(f"  Warnings: {'; '.join(pack.environment.warnings)}")

    # Schema
    if pack.schema_context.selected_tables:
        parts.append(f"- **Schema Tables**: {', '.join(pack.schema_context.selected_tables)}")
    if pack.schema_context.candidate_columns:
        parts.append(f"- **Candidate Columns**: {', '.join(pack.schema_context.candidate_columns[:15])}")
    if pack.schema_context.ddl_snippet:
        parts.append(f"- **DDL**:\n```sql\n{pack.schema_context.ddl_snippet[:3000]}\n```")

    # SQL
    if pack.sql.sql:
        parts.append(f"- **Current SQL**:\n```sql\n{pack.sql.sql}\n```")

    # Safety
    if pack.safety.passed is not None:
        parts.append(
            f"- **Safety**: can_execute={pack.safety.can_execute}, "
            f"requires_confirmation={pack.safety.requires_confirmation}"
        )
    if pack.safety.blocked_reasons:
        parts.append(f"  Blocked: {'; '.join(pack.safety.blocked_reasons)}")

    # Execution
    if pack.execution.columns:
        parts.append(
            f"- **Execution**: success={pack.execution.success}, "
            f"rows={pack.execution.row_count}"
        )
    if pack.execution.error:
        parts.append(f"  Error: {pack.execution.error}")

    # Result
    if pack.result.total_rows > 0:
        parts.append(f"- **Results**: {pack.result.query_count} queries, {pack.result.total_rows} rows")

    # Error
    if pack.run_state.error:
        parts.append(f"- **Error**: {pack.run_state.error}")

    # Recent run artifacts
    if pack.recent_activity.artifact_summaries:
        parts.append(
            f"- **Run Artifacts**: {', '.join(pack.recent_activity.artifact_summaries[-5:])}"
        )

    # Constraints
    if pack.constraints.requires_approval:
        parts.append("- **Constraints**: execution requires user approval")

    # Skill guidance
    if pack.skill.skill_summary:
        parts.append(f"- **Plan**: {pack.skill.skill_summary}")

    return "\n".join(parts)


def render_for_judge(pack: ContextPack) -> str:
    """Progress Judge view: focused on execution status, errors, and completion signals."""
    parts: list[str] = []

    parts.append(f"step={pack.run_state.step_count}/{pack.run_state.max_steps}, "
                 f"status={pack.run_state.status}")

    if pack.sql.sql:
        parts.append(f"SQL present: {pack.sql.sql_size} chars")

    if pack.safety.passed is not None:
        parts.append(
            f"Safety: can_execute={pack.safety.can_execute}, "
            f"requires_confirmation={pack.safety.requires_confirmation}"
        )

    if pack.execution.columns:
        parts.append(
            f"Execution: success={pack.execution.success}, "
            f"rows={pack.execution.row_count}"
        )

    if pack.result.total_rows > 0:
        parts.append(f"Results: {pack.result.non_empty_queries}/{pack.result.query_count} queries, {pack.result.total_rows} rows")
    if pack.result.chart_type:
        parts.append(f"Chart: {pack.result.chart_type}")

    if pack.run_state.error:
        parts.append(f"Error: {pack.run_state.error[:300]}")

    if pack.skill.selected_skill_ids:
        parts.append(f"Skills: {', '.join(pack.skill.selected_skill_ids)}")

    if pack.memory.recovery_hints:
        parts.append(pack.memory.recovery_hints)

    return " | ".join(parts)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return str(value)


def _normalize_str_list(items: list[Any]) -> list[str]:
    result: list[str] = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.append(str(item.get("text") or item))
        else:
            result.append(str(item))
    return result


def build_streaming_context_summary(state: dict[str, Any]) -> str:
    """Compact live summary for SSE context updates during a run."""
    parts: list[str] = []

    pack_raw = state.get("context_pack")
    if isinstance(pack_raw, dict):
        ui = pack_raw.get("ui_summary")
        if isinstance(ui, str) and ui.strip():
            parts.append(ui.strip())
        elif pack_raw:
            try:
                pack = ContextPack.model_validate(pack_raw)
                summary = render_ui_summary(pack)
                if summary:
                    parts.append(summary)
            except Exception:
                pass

    visible = state.get("visible_plan") or {}
    if isinstance(visible, dict):
        focus = visible.get("current_focus")
        if isinstance(focus, str) and focus.strip():
            if not parts or focus.strip() not in parts[0]:
                parts.append(f"Focus: {focus.strip()}")

    if state.get("repair_mode"):
        parts.append("Repair mode")

    repair_trace = state.get("repair_trace") or []
    if isinstance(repair_trace, list) and repair_trace:
        last = repair_trace[-1]
        if isinstance(last, dict) and last.get("user_visible_update"):
            note = str(last["user_visible_update"])
            if note not in " ".join(parts):
                parts.append(note)

    return " | ".join(parts)


def render_ui_summary(pack: ContextPack) -> str:
    """Short user-facing summary of context used — not the full ContextPack."""
    bits: list[str] = []
    table_count = len(pack.workspace.selected_tables) or (1 if pack.workspace.active_table else 0)
    schema_count = len(pack.schema_context.selected_tables)
    if table_count:
        bits.append(f"{table_count} workspace table{'s' if table_count != 1 else ''}")
    if schema_count:
        bits.append(f"{schema_count} schema table{'s' if schema_count != 1 else ''}")
    if pack.workspace.selected_columns:
        bits.append(f"{len(pack.workspace.selected_columns)} columns")
    if pack.workspace.active_sql:
        bits.append("SQL editor")
    if pack.sql.sql:
        bits.append("agent SQL")
    if pack.recent_activity.artifact_summaries:
        bits.append(f"{len(pack.recent_activity.artifact_summaries)} artifacts")
    if not bits:
        return "Minimal workspace context"
    return "Using " + ", ".join(bits)


def _first_user_message(state: dict[str, Any]) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    first = messages[0]
    content = getattr(first, "content", first if isinstance(first, dict) else "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        return " ".join(parts).strip()
    return str(content or "").strip()


def _open_tab_sql(ws_raw: Any) -> list[str]:
    if not isinstance(ws_raw, dict):
        return []
    tabs = ws_raw.get("open_sql_tabs") or []
    result: list[str] = []
    for tab in tabs[:6]:
        if isinstance(tab, dict) and tab.get("sql"):
            result.append(str(tab["sql"]))
        else:
            result.append("")
    return result


def _normalize_term_list(items: list[Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            result.append({
                "term": str(item.get("term") or item.get("name") or ""),
                "mapping": str(item.get("mapping") or item.get("definition") or ""),
            })
    return result
