from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def _to_iso(v: Any) -> str | None:
    if v is None: return None
    if isinstance(v, datetime): return v.isoformat()
    return str(v)


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
    sql: str
    datasource_id: str | None = None


class SQLExecuteRequest(BaseModel):
    datasource_id: str
    sql: str
    question: str | None = None
    execution_id: str | None = None


class SQLCancelRequest(BaseModel):
    execution_id: str


class SQLExplainRequest(BaseModel):
    datasource_id: str
    sql: str
