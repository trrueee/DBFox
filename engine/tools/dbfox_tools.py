from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.agent.plan import PlanStep, PlanStepStatus
from engine.tools.chart_suggestion import suggest_plotly_chart
from engine.sql.result_view.models import ResultPageQuery, ResultSourceRef
from engine.sql.result_view.service import ResultViewService
from engine.models import AgentArtifactRecord
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
    db_search,
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
    query: str = Field(description="A semantic search expression for table names, column names, comments, aliases, and AI-enriched descriptions. Before calling, expand the user's wording with Chinese synonyms, English schema terms, abbreviations, and possible table or column names; use one expression per call, and make multiple db.search calls for multiple candidate expressions.")
    limit: int = Field(default=20, description="Max results to return.")


class InspectInput(BaseModel):
    target: str = Field(description='Table or column to inspect, e.g. "users" or "users.email".')


class PreviewInput(BaseModel):
    table: str = Field(description="Table name to preview.")
    columns: list[str] | None = Field(default=None, description="Specific columns to include (omit for all).")
    limit: int = Field(default=10, description="Max rows to return.")
    where: dict[str, Any] | None = Field(default=None, description="Structured filter: {column, op, value}.")
    order_by: dict[str, Any] | list[dict[str, Any]] | None = Field(default=None, description="Structured sort: {column, direction} or [{...}].")


class SqlValidateInput(BaseModel):
    sql: str = Field(description="A single SELECT statement to validate against safety policies, schema cache, and syntax check.")
    question: str | None = Field(default=None, description="The original user question this SQL answers.")


class SqlExecuteReadonlyInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str | None = Field(default=None, description="The original user question this SQL answers.")


class EscalateInput(BaseModel):
    group: str = Field(description="Tool group to request access to.")
    reason: str = Field(default="", description="Why this group is needed for the current task.")


class QuestionRequestInput(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=4_000,
        description="One concise business clarification needed before the analysis can continue.",
    )
    reason: str = Field(
        min_length=1,
        max_length=2_000,
        description="Why verified analysis cannot proceed safely without this answer.",
    )
    options: list[dict[str, str]] = Field(
        default_factory=list,
        max_length=12,
        description="Optional choices. Each item has value, label, and optional description.",
    )
    allow_free_text: bool = Field(
        default=True,
        description="Whether the user may provide an answer outside the listed options.",
    )


class AnalysisCoverageInput(BaseModel):
    goal: str = Field(min_length=1, max_length=500, description="A user goal that has been addressed.")
    conclusion: str = Field(min_length=1, max_length=1_000, description="The concise supported conclusion.")
    artifact_ids: list[str] = Field(
        min_length=1, max_length=12,
        description="Observed result Artifact IDs that support this goal.",
    )


class AnalysisReviewInput(BaseModel):
    goal: str = Field(min_length=1, max_length=1_000, description="The user's overall analytical goal.")
    coverage: list[AnalysisCoverageInput] = Field(
        min_length=1, max_length=12,
        description="Goals already covered by verified result Artifacts.",
    )
    remaining: list[str] = Field(
        default_factory=list, max_length=12,
        description="Material unresolved goals. Keep empty only when the analysis is ready to synthesize.",
    )
    confidence: str = Field(
        pattern="^(low|medium|high)$",
        description="Confidence after considering data quality and remaining gaps.",
    )


class PlanUpdateInput(BaseModel):
    objective: str = Field(min_length=1, max_length=1_000)
    steps: list[PlanStep] = Field(min_length=1, max_length=12)
    summary: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def validate_plan_shape(self) -> "PlanUpdateInput":
        ids = [step.id for step in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("Task Plan step IDs must be unique")
        if sum(step.status is PlanStepStatus.IN_PROGRESS for step in self.steps) > 1:
            raise ValueError("Task Plan can have at most one in-progress step")
        return self


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


class ChartSuggestInput(BaseModel):
    force: bool = Field(default=False, description="Force chart generation even if data seems unsuitable.")


class ArtifactInspectInput(BaseModel):
    artifact_id: str = Field(description="Result or chart Artifact ID to inspect through the live Result Gateway.")
    page: int = Field(default=1, ge=1, description="Result page to load.")
    page_size: int = Field(default=50, ge=1, le=50, description="Rows to expose to this ReAct step only.")


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
            "environment", "schema", "db", "semantic",
            "execution", "result", "chart", "sql",
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


class RequestQuestionTool(BaseTool[QuestionRequestInput, LooseOutput]):
    name = "question.request"
    group = "control"
    description = (
        "Pause the current analysis and ask the user for missing business information. "
        "Use only when database exploration cannot resolve the ambiguity. This is not "
        "an authorization request and must never be used to approve a tool action."
    )
    input_model = QuestionRequestInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="none", risk_level="safe")
    execution = ToolExecutionSpec(idempotent=True)
    state = ToolStateSpec()
    artifacts = ArtifactSpec()

    def run(self, tool_input: QuestionRequestInput, context: ToolRunContext) -> LooseOutput:
        raise RuntimeError("question.request is settled by the Session runtime")


class AnalysisReviewTool(BaseTool[AnalysisReviewInput, LooseOutput]):
    name = "analysis.review"
    group = "control"
    description = (
        "Review whether a non-trivial data analysis has covered the user's goals before final synthesis. "
        "Link each covered goal to observed result Artifact IDs and list material remaining work. "
        "This does not finish the Run; the Runtime independently validates the proposal."
    )
    input_model = AnalysisReviewInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="none", risk_level="safe")
    execution = ToolExecutionSpec(idempotent=True)
    state = ToolStateSpec(produces=("analysis_review",), merge_strategy="new")
    artifacts = ArtifactSpec()

    def run(self, tool_input: AnalysisReviewInput, context: ToolRunContext) -> LooseOutput:
        artifact_ids: list[str] = []
        for coverage in tool_input.coverage:
            for artifact_id in coverage.artifact_ids:
                artifact = context.db_session.get(AgentArtifactRecord, artifact_id)
                if (
                    artifact is None
                    or str(artifact.session_id) != str(context.request.session_id)
                    or str(artifact.run_id) != str(context.request.run_id)
                    or str(artifact.type) != "result_view"
                ):
                    raise RuntimeError(f"Analysis coverage references an unavailable result Artifact: {artifact_id}")
                if artifact_id not in artifact_ids:
                    artifact_ids.append(artifact_id)
        return LooseOutput.model_validate({
            "ready": not tool_input.remaining,
            "goal": tool_input.goal,
            "coverage": [item.model_dump(mode="json") for item in tool_input.coverage],
            "remaining": tool_input.remaining,
            "confidence": tool_input.confidence,
            "artifactIds": artifact_ids,
        })


class PlanUpdateTool(BaseTool[PlanUpdateInput, LooseOutput]):
    name = "plan.update"
    group = "control"
    description = (
        "Create or meaningfully revise the visible analysis plan for a multi-part task. "
        "The plan is dynamic progress state, not a fixed workflow: keep stable step IDs, "
        "mark at most one step in progress, and attach real Artifact IDs to completed evidence steps."
    )
    input_model = PlanUpdateInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="none", risk_level="safe")
    execution = ToolExecutionSpec(capabilities=("metadata_write",))
    state = ToolStateSpec(produces=("analysis_plan",), merge_strategy="new")
    artifacts = ArtifactSpec()

    def run(self, tool_input: PlanUpdateInput, context: ToolRunContext) -> LooseOutput:
        return LooseOutput.model_validate({
            "objective": tool_input.objective,
            "steps": [step.model_dump(mode="json") for step in tool_input.steps],
            "summary": tool_input.summary,
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
    execution = ToolExecutionSpec(capabilities=("metadata_write", "database_read"))
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
        "match reasons and search trace fields. Before calling, rewrite the user's "
        "question into semantic search expressions that include original terms, "
        "Chinese synonyms, English schema terms, abbreviations, and possible table "
        "or column names. Use separate db.search calls for entity/domain terms, "
        "action/event terms, and schema-language terms, then compare candidates "
        "before inspecting tables."
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
    execution = ToolExecutionSpec(capabilities=("database_read",))
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
        "Execute the last SQL statement that passed sql.validate, using the validated safe_sql from agent state. "
        "Requires a successful sql.validate call in the current session. "
        "Do not pass SQL text to this tool. If manual confirmation is required, this tool will trigger an approval interrupt."
    )
    input_model = SqlExecuteReadonlyInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="read", risk_level="warning", requires_validated_sql=True)
    execution = ToolExecutionSpec(capabilities=("metadata_read", "database_read"))
    state = ToolStateSpec(
        consumes=("safety", "sql", "execution_id"),
        produces=("execution",),
        clear_on_success=("error", "last_error_telemetry", "last_failed_tool_call"),
        merge_strategy="new",
    )
    artifacts = ArtifactSpec(emit=True, artifact_types=("table",))

    def run(self, tool_input: SqlExecuteReadonlyInput, context: ToolRunContext) -> LooseOutput:
        from engine.tools.db_tools import sql_execute_readonly
        ignored_model_sql = str(context.raw_input.get("ignored_model_sql") or "").strip() or None
        return LooseOutput.model_validate(sql_execute_readonly(
            context.db_session, context.request.datasource_id,
            question=tool_input.question or "",
            safety=context.state.get("safety"),
            ignored_model_sql=ignored_model_sql,
            execution_id=str(context.state.get("execution_id") or "") or None,
            expected_connection_generation=getattr(
                context.request,
                "datasource_generation",
                None,
            ),
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
    policy = ToolPolicy(side_effect="read", risk_level="safe")
    execution = ToolExecutionSpec(capabilities=("metadata_read", "database_read"))
    state = ToolStateSpec(consumes=("latest_result_artifact_id",), produces=("chart_suggestion",), merge_strategy="new")
    artifacts = ArtifactSpec(emit=True, artifact_types=("chart",))

    def run(self, tool_input: ChartSuggestInput, context: ToolRunContext) -> LooseOutput:
        artifact_id = str(context.state.get("latest_result_artifact_id") or "").strip()
        if not artifact_id:
            raise RuntimeError("No query result artifact is available for chart suggestion.")
        service = ResultViewService(context.db_session)
        page = service.page(ResultPageQuery(
            source=ResultSourceRef(artifact_id=artifact_id),
            page=1,
            page_size=500,
            count_mode="none",
        ))
        execution = {
            "success": True,
            "columns": page.columns,
            "rows": page.rows,
            "rowCount": page.row_count if page.row_count is not None else len(page.rows),
            "truncated": page.has_next_page,
        }
        return LooseOutput.model_validate(suggest_plotly_chart(execution))


class ArtifactInspectTool(BaseTool[ArtifactInspectInput, LooseOutput]):
    name = "artifact.inspect"
    group = "result"
    description = (
        "Inspect a result or chart Artifact by ID. The gateway re-executes its verified source SQL and "
        "returns one short-lived page for the current reasoning step; rows are never persisted in memory."
    )
    input_model = ArtifactInspectInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="read", risk_level="safe")
    execution = ToolExecutionSpec(capabilities=("metadata_read", "database_read"))
    state = ToolStateSpec()
    artifacts = ArtifactSpec()

    def run(self, tool_input: ArtifactInspectInput, context: ToolRunContext) -> LooseOutput:
        artifact = context.db_session.get(AgentArtifactRecord, tool_input.artifact_id)
        if artifact is None or str(artifact.session_id) != str(context.request.session_id):
            raise RuntimeError("Artifact is unavailable in the current session.")
        service = ResultViewService(context.db_session)
        source = service.load_verified_source(ResultSourceRef(artifact_id=tool_input.artifact_id))
        page = service.page(ResultPageQuery(
            source=ResultSourceRef(artifact_id=tool_input.artifact_id),
            page=tool_input.page,
            page_size=tool_input.page_size,
            count_mode="estimate",
        ))
        return LooseOutput.model_validate({
            "artifact_id": tool_input.artifact_id,
            "queryFingerprint": source.fingerprint,
            "columns": page.columns,
            "rows": page.rows,
            "page": page.page,
            "page_size": page.page_size,
            "rowCount": page.row_count,
            "returnedRows": len(page.rows),
            "hasNextPage": page.has_next_page,
            "latencyMs": page.latency_ms,
            "warnings": page.warnings or [],
            "notices": page.notices or [],
        })


# ── Registry ───────────────────────────────────────────────────────────────────


def register_dbfox_tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(EscalateTool())
    registry.register(RequestQuestionTool())
    registry.register(AnalysisReviewTool())
    registry.register(PlanUpdateTool())
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
    registry.register(SqlValidateTool())
    registry.register(SqlExecuteReadonlyTool())
    registry.register(ArtifactInspectTool())
    registry.register(ChartSuggestTool())
    return registry
