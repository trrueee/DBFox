"""ContextPack — structured, multi-view context container for DataBox Agent v2.

Instead of each node (Planner, Model, Progress Judge) independently building
context from raw state, the ContextPack is assembled once after each observe
cycle and rendered into node-specific views.

Structure:
    ContextPack
    ├─ workspace     — current datasource / table / SQL / result / error
    ├─ environment    — env tier / dialect / catalog / warnings
    ├─ schema         — selected tables / columns / DDL
    ├─ semantic       — business terms / metrics / dimensions / join paths
    ├─ query_plan     — structured query plan artifact
    ├─ sql            — current SQL candidate
    ├─ safety         — TrustGate / guardrail result
    ├─ execution      — query execution result
    ├─ result         — result profile / facts / anomalies
    ├─ memory         — relevant memories (auto-injected)
    ├─ run_state      — step count / retry history / error
    └─ skill          — active skill guidance
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Section models ─────────────────────────────────────────────────────────────


class WorkspaceSection(BaseModel):
    datasource_id: str = ""
    active_sql: str | None = None
    active_table: str | None = None
    has_result: bool = False
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


class SemanticSection(BaseModel):
    resolved_terms: list[dict[str, str]] = Field(default_factory=list)
    resolved_metrics: list[dict[str, str]] = Field(default_factory=list)
    join_paths: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    context_text: str | None = None


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
    row_count: int = 0
    notable_facts: list[str] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
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


# ── ContextPack ────────────────────────────────────────────────────────────────


class ContextPack(BaseModel):
    """Structured context assembled after each observe cycle.

    Consumed by Planner, Model, and Progress Judge — each via its own
    renderer that selects and formats the relevant sections.
    """

    workspace: WorkspaceSection = Field(default_factory=WorkspaceSection)
    environment: EnvironmentSection = Field(default_factory=EnvironmentSection)
    schema: SchemaSection = Field(default_factory=SchemaSection)
    semantic: SemanticSection = Field(default_factory=SemanticSection)
    sql: SqlSection = Field(default_factory=SqlSection)
    safety: SafetySection = Field(default_factory=SafetySection)
    execution: ExecutionSection = Field(default_factory=ExecutionSection)
    result: ResultSection = Field(default_factory=ResultSection)
    memory: MemorySection = Field(default_factory=MemorySection)
    run_state: RunStateSection = Field(default_factory=RunStateSection)
    skill: SkillSection = Field(default_factory=SkillSection)

    @property
    def has_data(self) -> bool:
        """True if the pack contains any non-trivial context beyond defaults."""
        return bool(
            self.schema.selected_tables
            or self.sql.sql
            or self.execution.success
            or self.result.notable_facts
            or self.semantic.resolved_terms
        )

    @property
    def is_failing(self) -> bool:
        """True if the run is in a failure state."""
        return bool(
            self.run_state.error
            or not self.execution.success
            or self.run_state.status in ("failed", "blocked")
        )


# ── Builder ────────────────────────────────────────────────────────────────────


def build_context_pack(state: dict[str, Any]) -> ContextPack:
    """Build a ContextPack from raw agent state.

    Called after each observe cycle.  All sections are populated
    from the current state snapshot — no side effects.
    """
    # -- Workspace -----------------------------------------------------------
    ws_raw = state.get("workspace_context") or {}
    workspace = WorkspaceSection(
        datasource_id=str(state.get("datasource_id") or ""),
        active_sql=_str_or_none(ws_raw.get("selected_sql") or ws_raw.get("active_sql")),
        active_table=ws_raw.get("active_table"),
        has_result=bool(ws_raw.get("has_result")),
        error_summary=_str_or_none(state.get("error")),
    )

    # -- Environment ---------------------------------------------------------
    env_raw = state.get("environment_profile") or {}
    env_warnings: list[str] = []
    raw_warnings = env_raw.get("warnings") or []
    for w in raw_warnings:
        env_warnings.append(str(w))

    environment = EnvironmentSection(
        env_tier=str(env_raw.get("env") or env_raw.get("env_tier") or "unknown"),
        dialect=str(env_raw.get("dialect") or "unknown"),
        catalog_status=str(env_raw.get("catalog_status") or "unknown"),
        table_count=int(env_raw.get("table_count") or 0),
        warnings=env_warnings[:5],
    )

    # -- Schema --------------------------------------------------------------
    schema_raw = state.get("schema_context") or {}
    selected_tables: list[str] = []
    if isinstance(schema_raw, dict):
        raw_tables = schema_raw.get("selected_tables") or []
        for t in raw_tables:
            selected_tables.append(str(t))
    schema = SchemaSection(
        selected_tables=selected_tables,
        ddl_snippet=_str_or_none(schema_raw.get("schema_context") if isinstance(schema_raw, dict) else None),
        ddl_size=int(schema_raw.get("schema_context_size") or 0) if isinstance(schema_raw, dict) else 0,
    )

    # -- Semantic ------------------------------------------------------------
    sem_raw = state.get("semantic_resolution") or {}
    if isinstance(sem_raw, dict):
        semantic = SemanticSection(
            resolved_terms=_normalize_term_list(sem_raw.get("resolved_terms") or []),
            resolved_metrics=_normalize_term_list(sem_raw.get("resolved_metrics") or []),
            join_paths=_normalize_str_list(sem_raw.get("join_paths") or []),
            ambiguity_flags=_normalize_str_list(sem_raw.get("ambiguity") or []),
            context_text=_str_or_none(sem_raw.get("semantic_context_text")),
        )
    else:
        semantic = SemanticSection()

    # -- SQL -----------------------------------------------------------------
    sql_raw = state.get("sql")
    sql_str: str | None = None
    if isinstance(sql_raw, str):
        sql_str = sql_raw
    elif isinstance(sql_raw, dict):
        sql_str = sql_raw.get("sql") or str(sql_raw)
    sql = SqlSection(sql=sql_str, sql_size=len(sql_str) if sql_str else 0)

    # -- Safety --------------------------------------------------------------
    safety_raw = state.get("safety") or {}
    safety = SafetySection(
        can_execute=bool(safety_raw.get("can_execute")),
        requires_confirmation=bool(safety_raw.get("requires_confirmation")),
        blocked_reasons=_normalize_str_list(safety_raw.get("blocked_reasons") or []),
        passed=bool(safety_raw.get("passed")),
    )

    # -- Execution -----------------------------------------------------------
    exec_raw = state.get("execution") or {}
    execution = ExecutionSection(
        success=bool(exec_raw.get("success")),
        row_count=int(exec_raw.get("rowCount") or 0),
        columns=_normalize_str_list(exec_raw.get("columns") or []),
        error=_str_or_none(exec_raw.get("error")),
        truncated=bool(exec_raw.get("truncated")),
    )

    # -- Result --------------------------------------------------------------
    result_raw = state.get("result_profile") or {}
    result = ResultSection(
        row_count=int(result_raw.get("row_count") or 0),
        notable_facts=_normalize_str_list(result_raw.get("notable_facts") or [])[:5],
        anomalies=_normalize_str_list(result_raw.get("anomalies") or [])[:3],
        chart_type=_str_or_none((state.get("chart_suggestion") or {}).get("type")),
    )

    # -- Memory --------------------------------------------------------------
    memory = MemorySection()

    # -- Run state -----------------------------------------------------------
    run_state = RunStateSection(
        step_count=int(state.get("step_count") or 0),
        max_steps=int(state.get("max_steps") or 20),
        retry_budget=int((state.get("progress_decision") or {}).get("retry_budget") or 0),
        replan_count=int(state.get("replan_count") or 0),
        revision_count=int(state.get("revision_count") or 0),
        status=str(state.get("status") or "running"),
        error=_str_or_none(state.get("error")),
    )

    # -- Skill ---------------------------------------------------------------
    skill_ids: list[str] = state.get("selected_skill_ids") or []
    plan = state.get("plan_directive") or {}
    skill = SkillSection(
        selected_skill_ids=skill_ids,
        skill_summary=plan.get("reasoning_summary", ""),
    )

    return ContextPack(
        workspace=workspace,
        environment=environment,
        schema=schema,
        semantic=semantic,
        sql=sql,
        safety=safety,
        execution=execution,
        result=result,
        memory=memory,
        run_state=run_state,
        skill=skill,
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

    if pack.schema.selected_tables:
        parts.append(f"Active tables: {', '.join(pack.schema.selected_tables[:10])}")

    if pack.skill.selected_skill_ids:
        parts.append(f"Active skills: {', '.join(pack.skill.selected_skill_ids)}")

    if pack.run_state.error:
        parts.append(f"Last error: {pack.run_state.error[:200]}")

    return "\n".join(parts)


def render_for_model(pack: ContextPack) -> str:
    """Model view: full context with all factual state for ReAct reasoning."""
    parts = ["### DataBox Current State"]

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
    if pack.schema.selected_tables:
        parts.append(f"- **Schema Tables**: {', '.join(pack.schema.selected_tables)}")
    if pack.schema.ddl_snippet:
        parts.append(f"- **DDL**:\n```sql\n{pack.schema.ddl_snippet[:3000]}\n```")

    # Semantic
    if pack.semantic.context_text:
        parts.append(f"- **Semantic Context**: {pack.semantic.context_text}")
    if pack.semantic.resolved_terms:
        terms = [f"{t.get('term', '?')} → {t.get('mapping', '?')}" for t in pack.semantic.resolved_terms[:5]]
        parts.append(f"- **Resolved Terms**: {', '.join(terms)}")

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
    if pack.result.notable_facts:
        facts = "; ".join(pack.result.notable_facts[:3])
        parts.append(f"- **Result Profile**: {facts}")

    # Error
    if pack.run_state.error:
        parts.append(f"- **Error**: {pack.run_state.error}")

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

    if pack.result.notable_facts:
        parts.append(f"Notable facts: {len(pack.result.notable_facts)}")
    if pack.result.anomalies:
        parts.append(f"Anomalies: {len(pack.result.anomalies)}")

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


def _normalize_term_list(items: list[Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            result.append({
                "term": str(item.get("term") or item.get("name") or ""),
                "mapping": str(item.get("mapping") or item.get("definition") or ""),
            })
    return result
