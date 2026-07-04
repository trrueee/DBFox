from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class ResultColumn(BaseModel):
    name: str
    type: str | None = None


class ResultSourceRef(BaseModel):
    datasource_id: str
    source_sql_artifact_id: str
    safe_sql: str


class TableSourceRef(BaseModel):
    datasource_id: str
    table_id: str | None = None
    table_name: str


class ResultFilter(BaseModel):
    column: str
    operator: ResultFilterOperator
    value: Any = None


class ResultSort(BaseModel):
    column: str
    direction: Literal["asc", "desc"]


class ResultViewQuery(BaseModel):
    source: ResultSourceRef
    filters: list[ResultFilter] = Field(default_factory=list)
    sort: list[ResultSort] = Field(default_factory=list)
    search: str | None = None


class ResultPageQuery(ResultViewQuery):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
    count_mode: Literal["none", "exact", "estimate"] = "none"


class ResultExportQuery(ResultViewQuery):
    format: Literal["csv"] = "csv"


class TableViewQuery(BaseModel):
    source: TableSourceRef
    filters: list[ResultFilter] = Field(default_factory=list)
    sort: list[ResultSort] = Field(default_factory=list)
    search: str | None = None


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
    dialect: str
    columns: list[ResultColumn]
    fingerprint: str

    @property
    def column_names(self) -> list[str]:
        return [column.name for column in self.columns if column.name]


class ResultPage(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    page: int
    page_size: int
    row_count: int | None = None
    has_next_page: bool
    executed_sql: str
    latency_ms: int
    warnings: list[str] | None = None
    notices: list[str] | None = None


class ResultViewError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status_code = status_code

