from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.schemas import _to_iso


class QueryHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question: str | None = None
    submitted_sql: str | None = None
    generated_sql: str | None = None
    safe_sql: str | None = None
    executed_sql: str | None = None
    guardrail_result: str | None = None
    guardrail_checks: str | None = None
    execution_status: str | None = None
    execution_time_ms: int | None = None
    rows_returned: int | None = None
    columns_returned: int | None = None
    error_message: str | None = None
    created_at: str | None = None

    @field_validator("created_at", mode="before")
    @classmethod
    def _iso_dates(cls, v: Any) -> str | None:
        return _to_iso(v)


class SQLValidateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    sql: str = Field(min_length=1, max_length=200_000)
    datasource_id: str | None = Field(default=None, min_length=1, max_length=128)


class SQLCancelRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    execution_id: str = Field(min_length=1, max_length=128)


class SQLExplainRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    datasource_id: str = Field(min_length=1, max_length=128)
    sql: str = Field(min_length=1, max_length=200_000)
