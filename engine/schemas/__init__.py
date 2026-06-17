from datetime import datetime
from typing import Any


def _to_iso(v: Any) -> str | None:
    """Convert a datetime or string value to ISO-8601 for JSON serialization."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


from engine.schemas.project import ProjectCreateRequest
from engine.schemas.backup import BackupCreateRequest
from engine.schemas.error import ErrorResponse
from engine.schemas.table_design import (
    TableDesignColumnRequest,
    TableDesignIndexRequest,
    TableDesignDDLRequest,
    TableDesignExecuteRequest,
    TableDesignDraftSaveRequest,
    TableDesignAIRequest,
    TestDataGenerateRequest,
)
from engine.schemas.datasource import DataSourceTestRequest, DataSourceCreateRequest, DataSourceUpdateRequest
from engine.schemas.query import SQLValidateRequest, SQLExecuteRequest, SQLCancelRequest, SQLExplainRequest
from engine.schemas.ai import SQLGenerateRequest, SchemaAlterationRequest, GoldenSQLCreateRequest, BenchmarkRequest
from engine.schemas.semantic import (
    SemanticAliasCreateRequest,
    SemanticAliasUpdateRequest,
    SemanticMetricCreateRequest,
    SemanticMetricUpdateRequest,
    SemanticDimensionCreateRequest,
    SemanticDimensionUpdateRequest,
    WorkspaceTableScopeUpdateRequest,
)

__all__ = [
    "ProjectCreateRequest",
    "BackupCreateRequest",
    "ErrorResponse",
    "TableDesignColumnRequest",
    "TableDesignIndexRequest",
    "TableDesignDDLRequest",
    "TableDesignExecuteRequest",
    "TableDesignDraftSaveRequest",
    "TableDesignAIRequest",
    "TestDataGenerateRequest",
    "DataSourceTestRequest",
    "DataSourceCreateRequest",
    "DataSourceUpdateRequest",
    "SQLValidateRequest",
    "SQLExecuteRequest",
    "SQLCancelRequest",
    "SQLExplainRequest",
    "SQLGenerateRequest",
    "SchemaAlterationRequest",
    "GoldenSQLCreateRequest",
    "BenchmarkRequest",
    "SemanticAliasCreateRequest",
    "SemanticAliasUpdateRequest",
    "SemanticMetricCreateRequest",
    "SemanticMetricUpdateRequest",
    "SemanticDimensionCreateRequest",
    "SemanticDimensionUpdateRequest",
    "WorkspaceTableScopeUpdateRequest",
]
