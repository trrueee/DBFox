from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.errors import DBFoxError


ResultFilterOperator = Literal[
    "equals",
    "not_equals",
    "contains",
    "starts_with",
    "ends_with",
    "gt",
    "gte",
    "lt",
    "lte",
    "is_null",
    "is_not_null",
    "in",
    "not_in",
]

ResultIdentifier = Annotated[str, Field(min_length=1, max_length=256)]
ResultSearch = Annotated[str, Field(max_length=512)]
ResultScalar = Annotated[str, Field(max_length=4_096)] | int | float | bool | None
ResultFilterValue = ResultScalar | Annotated[list[ResultScalar], Field(max_length=100)]


class ResultViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResultColumn(ResultViewModel):
    name: ResultIdentifier
    type: Annotated[str, Field(max_length=256)] | None = None


class ResultSourceRef(ResultViewModel):
    artifact_id: ResultIdentifier


class TableSourceRef(ResultViewModel):
    datasource_id: ResultIdentifier
    table_id: ResultIdentifier | None = None
    table_name: ResultIdentifier


class ResultFilter(ResultViewModel):
    column: ResultIdentifier
    operator: ResultFilterOperator
    value: ResultFilterValue = None


class ResultSort(ResultViewModel):
    column: ResultIdentifier
    direction: Literal["asc", "desc"]


class ResultViewQuery(ResultViewModel):
    source: ResultSourceRef
    filters: list[ResultFilter] = Field(default_factory=list, max_length=16)
    sort: list[ResultSort] = Field(default_factory=list, max_length=16)
    search: ResultSearch | None = None


class ResultPageQuery(ResultViewQuery):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
    count_mode: Literal["none", "exact", "estimate"] = "none"


class ResultExportQuery(ResultViewQuery):
    format: Literal["csv"] = "csv"


class TableViewQuery(ResultViewModel):
    source: TableSourceRef
    filters: list[ResultFilter] = Field(default_factory=list, max_length=16)
    sort: list[ResultSort] = Field(default_factory=list, max_length=16)
    search: ResultSearch | None = None


class TablePageQuery(TableViewQuery):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
    count_mode: Literal["none", "exact", "estimate"] = "none"


class TableExportQuery(TableViewQuery):
    format: Literal["csv"] = "csv"


class VerifiedResultSource(BaseModel):
    datasource_id: str
    source_sql_artifact_id: str
    safe_sql: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    dialect: str
    columns: list[ResultColumn]
    fingerprint: str
    datasource_generation: str | int
    original_executed_at: str | None = None

    @property
    def column_names(self) -> list[str]:
        return [column.name for column in self.columns if column.name]


class ResultPage(ResultViewModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    page: int
    page_size: int
    row_count: int | None = None
    has_next_page: bool
    latency_ms: int
    consistency: Literal["live_reexecution", "live_query"]
    original_executed_at: str | None = None
    view_executed_at: str
    view_execution_id: str
    datasource_generation: str | int
    query_fingerprint: str
    warnings: list[str] | None = None
    notices: list[str] | None = None


class ChartData(ResultViewModel):
    series: list[dict[str, Any]]
    sample_size: int
    truncated: bool = False
    consistency: Literal["live_reexecution"] = "live_reexecution"
    original_executed_at: str | None = None
    view_executed_at: str
    view_execution_id: str
    datasource_generation: str | int
    query_fingerprint: str


class ResultViewError(DBFoxError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        try:
            public_code = FixedErrorCode(code)
        except ValueError:
            public_code = FixedErrorCode.INTERNAL_ERROR
        super().__init__(
            fixed_error_message(public_code),
            code=public_code.value,
        )
        # Retain diagnostic context without rendering it through Exception,
        # ToolResult, API Problem Details, or model-visible observations.
        self.internal_message = message
        self.status_code = status_code

