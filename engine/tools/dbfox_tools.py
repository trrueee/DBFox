from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engine.agent_core.answer import synthesize_agent_answer
from engine.agent_core.chart_builder import suggest_plotly_chart
from engine.agent_core.types import AgentAnswer
from engine.environment.tools import (
    environment_get_profile,
    schema_describe_table,
    schema_list_tables,
    schema_list_tables_page,
    schema_expand_related_tables,
    schema_refresh_catalog,
)
from engine.tools.db_tools import (
    db_inspect,
    db_observe,
    db_query,
    db_remember,
    db_search,
)
from engine.tools.memory_tools import (
    memory_delete,
    memory_search,
    memory_summarize_session,
    memory_write,
)
from engine.tools.runtime import (
    ArtifactSpec,
    BaseTool,
    ToolExecutionSpec,
    ToolPolicy,
    ToolRegistry,
    ToolRunContext,
    ToolStateSpec,
)
from engine.tools.db.preview import db_preview


# ── Output ────────────────────────────────────────────────────────────────────

class LooseOutput(BaseModel):
    """Output model for tools whose result shape is handler-defined."""
    model_config = ConfigDict(extra="allow")


# ── Input models ───────────────────────────────────────────────────────────────


class EmptyInput(BaseModel):
    """Tool takes no arguments."""


class SearchInput(BaseModel):
    query: str = Field(description="A semantic search expression for table names, column names, comments, aliases, and AI-enriched descriptions; use one expression per call, and make multiple db.search calls for multiple candidate expressions.")
    limit: int = Field(default=20, description="Max results to return.")


class InspectInput(BaseModel):
    target: str = Field(description='Table or column to inspect, e.g. "users" or "users.email".')


class PreviewInput(BaseModel):
    table: str = Field(description="Table name to preview.")
    columns: list[str] | None = Field(default=None, description="Specific columns to include (omit for all).")
    limit: int = Field(default=10, description="Max rows to return.")
    where: dict[str, Any] | None = Field(default=None, description="Structured filter: {column, op, value}.")
    order_by: dict[str, Any] | list[dict[str, Any]] | None = Field(default=None, description="Structured sort: {column, direction} or [{...}].")


class QueryInput(BaseModel):
    sql: str = Field(description="A single read-only SELECT statement to execute through TrustGate safety validation.")
    question: str | None = Field(default=None, description="The original user question this SQL answers.")


class SqlValidateInput(BaseModel):
    sql: str = Field(description="A single SELECT statement to validate against safety policies, schema cache, and syntax check.")
    question: str | None = Field(default=None, description="The original user question this SQL answers.")


class SqlExecuteReadonlyInput(BaseModel):
    sql: str = Field(description="The exact SELECT SQL statement to execute. Must match the validated safe_sql or original_sql from sql.validate.")
    question: str | None = Field(default=None, description="The original user question this SQL answers.")


class RememberInput(BaseModel):
    type: str = Field(description="Memory type: table_alias, column_alias, column_values, join_path, business_definition.")
    target: str = Field(description="Table or column name this memory is about.")
    evidence: str = Field(default="", description="Evidence or description of the discovery.")
    aliases: list[str] | None = Field(default=None, description="Alias names (for table_alias/column_alias).")
    value: Any | None = Field(default=None, description="Value payload: alias string, values list, join dict, or definition dict.")
    content: dict[str, Any] | None = Field(default=None, description="Structured metadata payload.")


class EscalateInput(BaseModel):
    group: str = Field(description="Tool group to request access to.")
    reason: str = Field(default="", description="Why this group is needed for the current task.")


class DescribeTableInput(BaseModel):
    table_name: str = Field(description="Name of the table to describe.")


class RefreshCatalogInput(BaseModel):
    reason: str = Field(default="", description="Why the catalog needs refreshing (e.g. 'tables appear missing').")


class ListTablesPageInput(BaseModel):
    offset: int = Field(default=0, description="Number of tables to skip.", ge=0)
    limit: int = Field(default=20, description="Max tables to return (1-100).", ge=1, le=100)
    name_filter: str | None = Field(default=None, description="Case-insensitive substring filter on table name.")


class ExpandRelatedTablesInput(BaseModel):
    table_name: str = Field(description="Seed table name to expand from.")
    depth: int = Field(default=1, description="How many FK hops to expand (only depth=1 supported currently).", ge=1, le=1)
    limit: int = Field(default=20, description="Max related tables to return.", ge=1, le=50)


class MemorySearchInput(BaseModel):
    query: str = Field(description="Search terms for finding relevant memories.")
    scope: list[str] | None = Field(default=None, description="Namespaces to search: user, datasource, project.")
    memory_types: list[str] | None = Field(default=None, description="Filter by memory type.")
    limit: int = Field(default=10, description="Max results.")


class MemoryWriteInput(BaseModel):
    type: str = Field(default="user_preference", description="Memory type: user_preference, schema_discovery, business_rule.")
    text: str = Field(description="What to remember, in natural language.")
    content: dict[str, Any] | None = Field(default=None, description="Optional structured metadata.")


class MemoryDeleteInput(BaseModel):
    memory_id: str = Field(description="ID of the memory record to delete.")
    reason: str = Field(default="user_requested", description="Why this memory is being deleted.")



class ChartSuggestInput(BaseModel):
    force: bool = Field(default=False, description="Force chart generation even if data seems unsuitable.")


class AnswerSynthesizeInput(BaseModel):
    question: str | None = Field(default=None, description="The original user question (uses session question if omitted).")


# ── Control ────────────────────────────────────────────────────────────────────


class EscalateTool(BaseTool[EscalateInput, LooseOutput]):
    name = "escalate.tool_group"
    group = "control"
    description = (
        "Request access to a tool group not currently available. "
        "Use when the current tool set is insufficient for the task. "
        "After escalation, the new group becomes available on the next call."
    )
    input_model = EscalateInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("allowed_tool_groups",))
    artifacts = ArtifactSpec()

    def run(self, tool_input: EscalateInput, context: ToolRunContext) -> LooseOutput:
        valid_groups = {
            "environment", "schema", "db", "semantic", "memory",
            "execution", "result", "chart", "answer", "sql",
        }
        group = tool_input.group.strip()
        reason = tool_input.reason.strip()
        if group not in valid_groups:
            raise RuntimeError(f"Unknown tool group '{group}'. Valid: {', '.join(sorted(valid_groups))}")
        current_groups = list(context.state.get("allowed_tool_groups") or [])
        if group in current_groups:
            return LooseOutput.model_validate({
                "escalated": False, "group": group, "reason": reason,
                "message": f"Group '{group}' is already available.",
            })
        return LooseOutput.model_validate({
            "escalated": True, "group": group, "reason": reason,
            "escalated_tool_groups": current_groups + [group],
        })


# ── Environment & Schema ───────────────────────────────────────────────────────


class EnvironmentGetProfileTool(BaseTool[EmptyInput, LooseOutput]):
    name = "environment.get_profile"
    group = "environment"
    description = "Return the datasource environment profile: dialect, version, catalog status, table count, and any configuration warnings."
    input_model = EmptyInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(produces=("environment_profile", "database_map"))
    artifacts = ArtifactSpec()

    def run(self, tool_input: EmptyInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(environment_get_profile(context.db_session, context.request.datasource_id))


class SchemaListTablesTool(BaseTool[EmptyInput, LooseOutput]):
    name = "schema.list_tables"
    group = "schema"
    description = "List all tables in the current datasource catalog with their column counts and estimated row counts."
    input_model = EmptyInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec()
    artifacts = ArtifactSpec()

    def run(self, tool_input: EmptyInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(schema_list_tables(context.db_session, context.request.datasource_id))


class SchemaDescribeTableTool(BaseTool[DescribeTableInput, LooseOutput]):
    name = "schema.describe_table"
    group = "schema"
    description = "Describe a single table: every column name, data type, nullability, default value, primary/foreign key flags, and column comment."
    input_model = DescribeTableInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec()
    artifacts = ArtifactSpec()

    def run(self, tool_input: DescribeTableInput, context: ToolRunContext) -> LooseOutput:
        try:
            result = schema_describe_table(context.db_session, context.request.datasource_id, tool_input.table_name)
            return LooseOutput.model_validate(result)
        except ValueError as e:
            raise RuntimeError(str(e))


class SchemaRefreshCatalogTool(BaseTool[RefreshCatalogInput, LooseOutput]):
    name = "schema.refresh_catalog"
    group = "schema"
    description = "Re-introspect the live datasource and update the local schema catalog. Use when tables appear to be missing or the catalog seems stale."
    input_model = RefreshCatalogInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec()
    artifacts = ArtifactSpec()

    def run(self, tool_input: RefreshCatalogInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(schema_refresh_catalog(context.db_session, context.request.datasource_id, tool_input.reason))


class SchemaListTablesPageTool(BaseTool[ListTablesPageInput, LooseOutput]):
    name = "schema.list_tables_page"
    group = "schema"
    description = (
        "Browse tables page-by-page without dumping the entire catalog. "
        "Accept an offset/limit pagination and an optional name_filter. "
        "Use this for large catalogs instead of schema.list_tables. "
        "Each page tells you if there are more pages (has_more)."
    )
    input_model = ListTablesPageInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(produces=("candidate_tables",))
    artifacts = ArtifactSpec()

    def run(self, tool_input: ListTablesPageInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(schema_list_tables_page(
            context.db_session,
            context.request.datasource_id,
            offset=tool_input.offset,
            limit=tool_input.limit,
            name_filter=tool_input.name_filter,
        ))


class SchemaExpandRelatedTablesTool(BaseTool[ExpandRelatedTablesInput, LooseOutput]):
    name = "schema.expand_related_tables"
    group = "schema"
    description = (
        "Find tables related to a given table through foreign keys. "
        "Returns both outgoing FK references (tables this one points to) "
        "and incoming FK references (tables that point to this one). "
        "Use this after discovering a candidate table to explore its "
        "neighbourhood without searching the entire catalog."
    )
    input_model = ExpandRelatedTablesInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(produces=("candidate_tables",))
    artifacts = ArtifactSpec()

    def run(self, tool_input: ExpandRelatedTablesInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(schema_expand_related_tables(
            context.db_session,
            context.request.datasource_id,
            table_name=tool_input.table_name,
            depth=tool_input.depth,
            limit=tool_input.limit,
        ))


# ── DB ─────────────────────────────────────────────────────────────────────────


class DbObserveTool(BaseTool[EmptyInput, LooseOutput]):
    name = "db.observe"
    group = "db"
    description = (
        "Get a high-level map of the database: schemas, tables grouped by "
        "business domain, column counts, primary keys, foreign keys, query "
        "history stats, and catalog freshness warnings. Use this FIRST to "
        "orient yourself before searching or inspecting specific objects."
    )
    input_model = EmptyInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(produces=("database_map",))
    artifacts = ArtifactSpec()

    def run(self, tool_input: EmptyInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(db_observe(context.db_session, context.request.datasource_id))


class DbSearchTool(BaseTool[SearchInput, LooseOutput]):
    name = "db.search"
    group = "db"
    description = (
        "Full-text search across table names, column names, comments, AI-enriched "
        "descriptions, business terms, and aliases. Returns scored results with "
        "match reasons. Use after db.observe to find relevant tables and columns "
        "for the user's question."
    )
    input_model = SearchInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(produces=("db_search_results",))
    artifacts = ArtifactSpec()

    def run(self, tool_input: SearchInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(db_search(context.db_session, context.request.datasource_id, tool_input.query, tool_input.limit))


class DbInspectTool(BaseTool[InspectInput, LooseOutput]):
    name = "db.inspect"
    group = "db"
    description = (
        "Live-inspect a single database object. For a table, returns every column "
        "with type, nullability, primary/foreign key relationships (both directions), "
        "indexes, and row count estimate. For a column, returns type details and "
        "foreign key target. Use to verify structure before writing SQL."
    )
    input_model = InspectInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(
        produces=("db_inspection",),
        clear_on_success=("error", "last_error_telemetry", "last_failed_tool_call"),
        merge_strategy="new",
    )
    artifacts = ArtifactSpec()

    def run(self, tool_input: InspectInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(db_inspect(context.db_session, context.request.datasource_id, tool_input.target))


class DbPreviewTool(BaseTool[PreviewInput, LooseOutput]):
    name = "db.preview"
    group = "db"
    description = (
        "Safely preview a small sample of real data rows from a table. "
        "Sensitive columns (PII, credentials) are automatically redacted. "
        "Use to confirm what the data actually looks like before writing SQL."
    )
    input_model = PreviewInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="read", risk_level="safe")
    execution = ToolExecutionSpec()
    state = ToolStateSpec(
        produces=("db_preview",),
        clear_on_success=("error", "last_error_telemetry", "last_failed_tool_call"),
    )
    artifacts = ArtifactSpec(emit=True, artifact_types=("table",))

    def run(self, tool_input: PreviewInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(db_preview(
            context.db_session,
            context.request.datasource_id,
            table=tool_input.table,
            columns=tool_input.columns,
            limit=tool_input.limit,
            where=tool_input.where,
            order_by=tool_input.order_by,
        ))


class DbQueryTool(BaseTool[QueryInput, LooseOutput]):
    name = "db.query"
    group = "db"
    description = (
        "Internal fast path for backend-owned read-only SELECT execution. "
        "This tool is not model-visible; model-authored SQL must use the "
        "explicit sql.validate then sql.execute_readonly lifecycle. "
        "The internal path still runs Guardrail, TrustGate, PolicyEngine, "
        "and sensitive-column redaction."
    )
    input_model = QueryInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="read", risk_level="warning", visible_to_model=False)
    execution = ToolExecutionSpec()
    state = ToolStateSpec(
        produces=("execution",),
        clear_on_success=("error", "last_error_telemetry", "last_failed_tool_call"),
    )
    artifacts = ArtifactSpec(emit=True, artifact_types=("table",))

    def run(self, tool_input: QueryInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(db_query(context.db_session, context.request.datasource_id, tool_input.sql, tool_input.question or ""))


class SqlValidateTool(BaseTool[SqlValidateInput, LooseOutput]):
    name = "sql.validate"
    group = "sql"
    description = (
        "Validate a SELECT SQL query against safety policies, schema cache, and syntax check. "
        "Does NOT execute the query or read real data. "
        "Always call this first before trying to execute any SQL query."
    )
    input_model = SqlValidateInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="none", risk_level="safe")
    execution = ToolExecutionSpec()
    state = ToolStateSpec(produces=("safety", "sql"), merge_strategy="new")
    artifacts = ArtifactSpec()

    def run(self, tool_input: SqlValidateInput, context: ToolRunContext) -> LooseOutput:
        from engine.tools.db_tools import sql_validate
        return LooseOutput.model_validate(sql_validate(
            context.db_session, context.request.datasource_id,
            tool_input.sql, tool_input.question or "",
        ))


class SqlExecuteReadonlyTool(BaseTool[SqlExecuteReadonlyInput, LooseOutput]):
    name = "sql.execute_readonly"
    group = "sql"
    description = (
        "Execute a read-only SELECT SQL statement using a previously validated safety decision. "
        "Requires a successful sql.validate call in the current session. "
        "If manual confirmation is required, this tool will trigger an approval interrupt."
    )
    input_model = SqlExecuteReadonlyInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="read", risk_level="warning", requires_validated_sql=True)
    execution = ToolExecutionSpec()
    state = ToolStateSpec(
        consumes=("safety", "sql"),
        produces=("execution",),
        clear_on_success=("error", "last_error_telemetry", "last_failed_tool_call"),
        merge_strategy="new",
    )
    artifacts = ArtifactSpec(emit=True, artifact_types=("table",))

    def run(self, tool_input: SqlExecuteReadonlyInput, context: ToolRunContext) -> LooseOutput:
        from engine.tools.db_tools import sql_execute_readonly
        return LooseOutput.model_validate(sql_execute_readonly(
            context.db_session, context.request.datasource_id,
            tool_input.sql, tool_input.question or "",
            safety=context.state.get("safety"),
        ))


class DbRememberTool(BaseTool[RememberInput, LooseOutput]):
    name = "db.remember"
    group = "db"
    description = (
        "Record a useful discovery for future searches: schema aliases, "
        "join paths, business definitions, or data quirks. Stored memories "
        "are searchable in later sessions via db.search and memory.search."
    )
    input_model = RememberInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="write", risk_level="warning", visible_to_model=False)
    execution = ToolExecutionSpec()
    state = ToolStateSpec(merge_strategy="new")
    artifacts = ArtifactSpec()

    def run(self, tool_input: RememberInput, context: ToolRunContext) -> LooseOutput:
        extra: dict[str, Any] = {}
        if tool_input.aliases:
            extra["aliases"] = tool_input.aliases
        if tool_input.value is not None:
            extra["value"] = tool_input.value
        if tool_input.content:
            extra.update(tool_input.content)
        return LooseOutput.model_validate(db_remember(
            context.db_session, context.request.datasource_id,
            mem_type=tool_input.type, target=tool_input.target,
            evidence=tool_input.evidence, **extra,
        ))


# ── Result / Chart / Answer ────────────────────────────────────────────────────



class ChartSuggestTool(BaseTool[ChartSuggestInput, LooseOutput]):
    name = "chart.suggest"
    group = "chart"
    description = (
        "Suggest a chart visualization for the current query result. "
        "Automatically picks chart type (bar/line/pie), label column, and "
        "value column based on column types and data shape."
    )
    input_model = ChartSuggestInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("execution",), produces=("chart_suggestion",), merge_strategy="new")
    artifacts = ArtifactSpec(emit=True, artifact_types=("chart",))

    def run(self, tool_input: ChartSuggestInput, context: ToolRunContext) -> LooseOutput:
        execution = context.state.get("execution")
        if not isinstance(execution, dict) or not execution.get("success"):
            raise RuntimeError("No successful execution result available for chart suggestion.")
        return LooseOutput.model_validate(suggest_plotly_chart(execution))


class AnswerSynthesizeTool(BaseTool[AnswerSynthesizeInput, AgentAnswer]):
    name = "answer.synthesize"
    group = "answer"
    description = (
        "Synthesize a structured final answer from all collected evidence: "
        "query results, profile, chart, safety decisions, and any errors. "
        "Produces an AgentAnswer with key findings, evidence references, "
        "caveats, recommendations, and follow-up questions."
    )
    input_model = AnswerSynthesizeInput
    output_model = AgentAnswer
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(
        consumes=("analysis_units", "error"),
        produces=("answer", "final_answer"),
        merge_strategy="always_new",
    )
    artifacts = ArtifactSpec(emit=True, artifact_types=("sql", "table", "chart"))

    def run(self, tool_input: AnswerSynthesizeInput, context: ToolRunContext) -> AgentAnswer:
        question = tool_input.question or getattr(context.request, "question", "") or ""
        model_name = getattr(context.request, "model_name", None)
        api_key = getattr(context.request, "api_key", None)
        api_base = getattr(context.request, "api_base", None)

        return synthesize_agent_answer(
            question=question,
            analysis_units=list(context.state.get("analysis_units") or []),
            model_name=model_name,
            api_key=api_key,
            api_base=api_base,
            error=context.state.get("error"),
        )


# ── Memory ─────────────────────────────────────────────────────────────────────


class MemorySearchTool(BaseTool[MemorySearchInput, LooseOutput]):
    name = "memory.search"
    group = "memory"
    description = "Search long-term memory for relevant context from past sessions: schema discoveries, business rules, user preferences, and join paths."
    input_model = MemorySearchInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("datasource_id", "user_id", "project_id", "thread_id", "session_id"))
    artifacts = ArtifactSpec()

    def run(self, tool_input: MemorySearchInput, context: ToolRunContext) -> LooseOutput:
        state = context.state
        return LooseOutput.model_validate(memory_search(
            query=tool_input.query,
            user_id=state.get("user_id") or state.get("thread_id"),
            datasource_id=state.get("datasource_id") or context.request.datasource_id,
            project_id=state.get("project_id"),
            scope=tool_input.scope,
            memory_types=tool_input.memory_types,
            limit=tool_input.limit,
        ))


class MemoryWriteTool(BaseTool[MemoryWriteInput, LooseOutput]):
    name = "memory.write"
    group = "memory"
    description = "Write a new entry to long-term memory. Use for discoveries that will be useful in future sessions: table relationships, business definitions, user preferences, or data quirks."
    input_model = MemoryWriteInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="write", risk_level="warning", visible_to_model=False)
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("datasource_id", "user_id", "project_id", "thread_id", "session_id"))
    artifacts = ArtifactSpec()

    def run(self, tool_input: MemoryWriteInput, context: ToolRunContext) -> LooseOutput:
        state = context.state
        return LooseOutput.model_validate(memory_write(
            mem_type=tool_input.type,
            text=tool_input.text,
            content=tool_input.content,
            user_id=state.get("user_id") or state.get("thread_id"),
            datasource_id=state.get("datasource_id") or context.request.datasource_id,
            project_id=state.get("project_id"),
        ))


class MemoryDeleteTool(BaseTool[MemoryDeleteInput, LooseOutput]):
    name = "memory.delete"
    group = "memory"
    description = "Delete a long-term memory entry by ID."
    input_model = MemoryDeleteInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="write", risk_level="warning", visible_to_model=False)
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("datasource_id", "user_id", "project_id", "thread_id", "session_id"))
    artifacts = ArtifactSpec()

    def run(self, tool_input: MemoryDeleteInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate(memory_delete(memory_id=tool_input.memory_id, reason=tool_input.reason))


class MemorySummarizeSessionTool(BaseTool[EmptyInput, LooseOutput]):
    name = "memory.summarize_session"
    group = "memory"
    description = "Summarize the current conversation session into a compact memory for future recall. Use at the end of a successful task."
    input_model = EmptyInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("datasource_id", "user_id", "project_id", "thread_id", "session_id"))
    artifacts = ArtifactSpec()

    def run(self, tool_input: EmptyInput, context: ToolRunContext) -> LooseOutput:
        session_id = str(context.state.get("thread_id") or context.state.get("session_id") or "")
        return LooseOutput.model_validate(memory_summarize_session(session_id=session_id))


# ── Registry ───────────────────────────────────────────────────────────────────


def register_dbfox_tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(EscalateTool())
    registry.register(EnvironmentGetProfileTool())
    registry.register(SchemaListTablesTool())
    registry.register(SchemaDescribeTableTool())
    registry.register(SchemaRefreshCatalogTool())
    registry.register(SchemaListTablesPageTool())
    registry.register(SchemaExpandRelatedTablesTool())
    registry.register(DbObserveTool())
    registry.register(DbSearchTool())
    registry.register(DbInspectTool())
    registry.register(DbPreviewTool())
    registry.register(DbQueryTool())
    registry.register(SqlValidateTool())
    registry.register(SqlExecuteReadonlyTool())
    registry.register(DbRememberTool())

    registry.register(ChartSuggestTool())
    registry.register(AnswerSynthesizeTool())
    registry.register(MemorySearchTool())
    registry.register(MemoryWriteTool())
    registry.register(MemoryDeleteTool())
    registry.register(MemorySummarizeSessionTool())
    return registry
