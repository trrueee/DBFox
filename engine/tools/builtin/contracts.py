from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from engine.agent.plan import PlanStep, PlanStepStatus
from engine.environment.inventory import InspectedColumnObject, InspectedTable
from engine.tools.db._common import MAX_PREVIEW_ROWS
from engine.tools.db.search import MAX_SEARCH_QUERY_CHARS
from engine.tools.runtime import ToolInputModel, ToolOutputModel


Identifier = Annotated[str, Field(min_length=1, max_length=256)]
ArtifactId = Annotated[str, Field(min_length=1, max_length=128)]
JsonObject = dict[str, JsonValue]


class EmptyInput(ToolInputModel):
    """This function takes no arguments."""


class AcknowledgementOutput(ToolOutputModel):
    acknowledged: bool = True


ConversationRole = Literal["user", "assistant"]


class ConversationSearchInput(ToolInputModel):
    query: str = Field(
        min_length=1,
        max_length=500,
        description="A literal phrase remembered from the current conversation.",
    )
    roles: list[ConversationRole] = Field(
        default_factory=lambda: ["user", "assistant"],
        min_length=1,
        max_length=2,
    )
    limit: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="after")
    def normalize_search(self) -> "ConversationSearchInput":
        query = self.query.strip()
        if not query:
            raise ValueError("Conversation search query must not be blank")
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("Conversation search roles must be unique")
        object.__setattr__(self, "query", query)
        return self


class ConversationSearchMatch(ToolOutputModel):
    message_id: str
    sequence: int = Field(ge=1)
    role: ConversationRole
    created_at: str
    snippet: str = Field(max_length=700)


class ConversationSearchOutput(ToolOutputModel):
    query: str
    searched_roles: list[ConversationRole]
    search_mode: Literal["fts5_trigram", "literal_scan"]
    matches: list[ConversationSearchMatch]
    returned_count: int = Field(ge=0)


class ConversationReadInput(ToolInputModel):
    after_sequence: int = Field(
        default=0,
        ge=0,
        description="Return messages after this sequence; use 0 for the beginning.",
    )
    limit: int = Field(default=10, ge=1, le=10)


class ConversationMessageOutput(ToolOutputModel):
    message_id: str
    sequence: int = Field(ge=1)
    role: ConversationRole
    created_at: str
    content: str = Field(max_length=4_000)
    truncated: bool


class ConversationReadOutput(ToolOutputModel):
    messages: list[ConversationMessageOutput]
    returned_count: int = Field(ge=0)
    has_more: bool
    next_after_sequence: int | None = Field(default=None, ge=1)


class CatalogOverviewOutput(ToolOutputModel):
    datasource_id: str
    datasource_name: str
    dialect: str
    catalog_status: str
    last_sync_at: str | None = None
    table_count: int = Field(ge=0)
    mode: Literal["summary", "full"]
    warnings: list[str] = Field(default_factory=list)
    schemas: list[JsonObject] = Field(default_factory=list)
    domains: list[JsonObject] = Field(default_factory=list)
    next_action_hint: str | None = None


class CatalogRefreshOutput(ToolOutputModel):
    datasource_id: str
    status: Literal["ready"]
    refreshed_at: str
    table_count: int = Field(ge=0)
    schema_count: int = Field(ge=0)
    tables_created: int = Field(ge=0)
    tables_updated: int = Field(ge=0)
    tables_removed: int = Field(ge=0)
    columns_created: int = Field(ge=0)
    columns_updated: int = Field(ge=0)
    columns_removed: int = Field(ge=0)


class SchemaListCursor(ToolInputModel):
    schema_name: str = Field(max_length=256)
    table_name: Identifier
    table_id: ArtifactId


class SchemaListInput(ToolInputModel):
    cursor: SchemaListCursor | None = Field(
        default=None,
        description="Exact cursor returned by the previous page; omit for the first page.",
    )
    limit: int = Field(default=20, ge=1, le=100)
    name_filter: str | None = Field(default=None, min_length=1, max_length=256)


class TableSummary(ToolOutputModel):
    table_id: str
    schema_name: str
    table_name: str
    qualified_name: str
    columns_count: int = Field(ge=0)
    row_count_estimate: int | None = Field(default=None, ge=0)
    table_type: str
    comment: str | None = None


class SchemaListOutput(ToolOutputModel):
    tables: list[TableSummary]
    next_cursor: SchemaListCursor | None = None
    returned_count: int = Field(ge=0)
    has_more: bool
    catalog_status: str


class SchemaSearchInput(ToolInputModel):
    queries: list[
        Annotated[
            str,
            Field(min_length=1, max_length=MAX_SEARCH_QUERY_CHARS),
        ]
    ] = Field(
        min_length=1,
        max_length=4,
        description=(
            "One to four concise semantic expressions. Include business terms and "
            "likely schema terms in the same call instead of repeating searches."
        ),
    )
    limit_per_query: int = Field(default=8, ge=1, le=20)

    @model_validator(mode="after")
    def normalize_unique_queries(self) -> "SchemaSearchInput":
        normalized = [query.strip() for query in self.queries]
        if any(not query for query in normalized):
            raise ValueError("Search queries must not be blank")
        if len({query.casefold() for query in normalized}) != len(normalized):
            raise ValueError("Search queries must be unique")
        object.__setattr__(self, "queries", normalized)
        return self


class SearchResultSet(ToolOutputModel):
    query: str
    engine: str
    tokens: list[str]
    results: list[JsonObject]
    returned_count: int = Field(ge=0)


class SchemaSearchOutput(ToolOutputModel):
    searches: list[SearchResultSet]
    candidates: list[JsonObject]
    returned_count: int = Field(ge=0)


class SchemaInspectInput(ToolInputModel):
    targets: list[Identifier] = Field(
        min_length=1,
        max_length=5,
        description='Tables or columns, for example ["orders", "orders.customer_id"].',
    )

    @model_validator(mode="after")
    def require_unique_targets(self) -> "SchemaInspectInput":
        normalized = [target.strip() for target in self.targets]
        if len({target.casefold() for target in normalized}) != len(normalized):
            raise ValueError("Inspection targets must be unique")
        object.__setattr__(self, "targets", normalized)
        return self


class SchemaInspection(ToolOutputModel):
    target: str
    details: Annotated[
        InspectedTable | InspectedColumnObject,
        Field(discriminator="object_type"),
    ]


class SchemaInspectOutput(ToolOutputModel):
    inspections: list[SchemaInspection]


FilterScalar = Annotated[str, Field(max_length=4_000)] | int | float | bool | None


class PreviewFilterInput(ToolInputModel):
    column: Identifier
    op: Literal[
        "=",
        "!=",
        "<>",
        "<",
        ">",
        "<=",
        ">=",
        "LIKE",
        "NOT LIKE",
        "ILIKE",
        "NOT ILIKE",
        "IN",
        "NOT IN",
        "IS",
        "IS NOT",
    ] = "="
    value: FilterScalar | Annotated[list[FilterScalar], Field(max_length=100)] = None


class PreviewOrderInput(ToolInputModel):
    column: Identifier
    direction: Literal["ASC", "DESC"] = "ASC"


class DataPreviewInput(ToolInputModel):
    table: Identifier
    columns: list[Identifier] | None = Field(default=None, max_length=32)
    limit: int = Field(default=10, ge=1, le=MAX_PREVIEW_ROWS)
    where: PreviewFilterInput | None = None
    order_by: list[PreviewOrderInput] | None = Field(default=None, max_length=8)


class DataPreviewOutput(ToolOutputModel):
    table: str
    columns: list[str]
    returned_rows: int = Field(ge=0)
    limit_applied: int = Field(ge=1, le=MAX_PREVIEW_ROWS)
    rows: list[JsonObject]
    safe_sql: str
    parameters: JsonObject = Field(default_factory=dict, exclude=True)
    truncated: bool
    warnings: list[str] = Field(default_factory=list)
    column_summaries: list[JsonObject] = Field(default_factory=list)
    audit: JsonObject
    latency_ms: int = Field(ge=0)


class SqlValidateInput(ToolInputModel):
    sql: str = Field(
        min_length=1,
        max_length=50_000,
        description="One read-only SELECT statement that answers the active user request.",
    )


class SqlValidateOutput(ToolOutputModel):
    can_execute: bool
    requires_confirmation: bool
    safe_sql: str
    original_sql: str
    risk_level: str
    blocked_reasons: list[str]
    messages: list[str]
    execution_safety_decision: JsonObject


class SqlExecuteReadonlyInput(ToolInputModel):
    validation_artifact_id: ArtifactId = Field(
        description="Exact SQL Artifact ID produced by sql_validate."
    )


class QueryResultOutput(ToolOutputModel):
    status: Literal["success"]
    success: Literal[True]
    row_count: int = Field(ge=0)
    columns: list[str]
    column_types: list[str]
    returned_rows: int = Field(ge=0)
    truncated: bool
    rows: list[JsonObject]
    safe_sql: str
    execution_time_ms: int | float = Field(ge=0)
    explain_plan: JsonValue | None = None
    warnings: list[str] = Field(default_factory=list)
    audit: JsonObject
    latency_ms: int = Field(ge=0)


class ResultInspectInput(ToolInputModel):
    result_artifact_id: ArtifactId
    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(
        default=20,
        ge=1,
        le=20,
        description=(
            "Bounded model observation page. Use a smaller page_size when the "
            "returned window reports response-byte truncation."
        ),
    )


class ResultInspectOutput(ToolOutputModel):
    result_artifact_id: str
    referenced_artifact_ids: list[str]
    query_fingerprint: str
    columns: list[str]
    rows: list[JsonObject]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    row_count: int | None = Field(default=None, ge=0)
    returned_rows: int = Field(ge=0)
    has_next_page: bool
    latency_ms: int | float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


class ResultProfileInput(ToolInputModel):
    result_artifact_id: ArtifactId
    columns: list[Identifier] = Field(
        default_factory=list,
        max_length=12,
        description=(
            "Optional result columns to profile. Leave empty to profile the first "
            "twelve columns in the verified result."
        ),
    )
    sample_size: int = Field(default=500, ge=20, le=500)
    top_k: int = Field(default=8, ge=1, le=20)

    @model_validator(mode="after")
    def validate_unique_columns(self) -> "ResultProfileInput":
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("columns must not contain duplicates")
        return self


class ResultProfileOutput(ToolOutputModel):
    result_artifact_id: str
    referenced_artifact_ids: list[str]
    query_fingerprint: str
    profiled_columns: list[str]
    profiles: list[JsonObject]
    sample_size: int = Field(ge=0)
    sample_truncated: bool
    warnings: list[str] = Field(default_factory=list)


class ChartCreateInput(ToolInputModel):
    result_artifact_id: ArtifactId
    intent: str | None = Field(
        default=None,
        min_length=1,
        max_length=1_000,
        description=(
            "Optional analytical intent for the chart. The runtime still verifies "
            "all selected fields against the referenced result."
        ),
    )
    chart_type: Literal["auto", "line", "bar", "pie", "scatter", "area"] = "auto"
    x: Identifier | None = None
    y: Identifier | None = None
    aggregation: Literal["auto", "sum", "none"] = "auto"
    title: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_explicit_axes(self) -> "ChartCreateInput":
        if (self.x is None) != (self.y is None):
            raise ValueError("x and y must be supplied together")
        if self.x is not None and self.x == self.y:
            raise ValueError("x and y must reference different result columns")
        return self


class ChartCreateOutput(ToolOutputModel):
    result_artifact_id: str
    chartable: bool
    chart_type: Literal["none", "line", "bar", "pie", "scatter", "area"]
    x: str | None = None
    y: str | None = None
    title: str | None = None
    reason: str
    aggregation: Literal["sum", "none"] | None = None
    sample_size: int | None = Field(default=None, ge=0)
    sample_truncated: bool = False
    query_fingerprint: str
    intent: str | None = None
    x_label: str | None = None
    y_label: str | None = None
    series_label: str | None = None
    data_label: bool | None = None
    dimensions: list[JsonObject] = Field(default_factory=list)
    metrics: list[JsonObject] = Field(default_factory=list)


class ClarificationOption(ToolInputModel):
    value: str = Field(min_length=1, max_length=500)
    label: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=1_000)


class RequestClarificationInput(ToolInputModel):
    question: str = Field(min_length=1, max_length=4_000)
    reason: str = Field(min_length=1, max_length=2_000)
    options: list[ClarificationOption] = Field(default_factory=list, max_length=12)
    allow_free_text: bool = True


class UpdatePlanInput(ToolInputModel):
    objective: str = Field(min_length=1, max_length=1_000)
    steps: list[PlanStep] = Field(min_length=1, max_length=12)
    summary: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def validate_plan_shape(self) -> "UpdatePlanInput":
        ids = [step.id for step in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("Plan step IDs must be unique")
        if sum(step.status is PlanStepStatus.IN_PROGRESS for step in self.steps) > 1:
            raise ValueError("Plan can have at most one in-progress step")
        return self


class UpdatePlanOutput(ToolOutputModel):
    plan_id: str
    version: int = Field(ge=1)
    objective: str
    steps: list[PlanStep]
    status: str
    summary: str | None = None
