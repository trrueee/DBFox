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
from engine.schemas.error import ErrorResponse, ProblemDetails
from engine.schemas.test_data import TestDataGenerateRequest
from engine.schemas.datasource import DataSourceTestRequest, DataSourceCreateRequest, DataSourceUpdateRequest
from engine.schemas.query import SQLValidateRequest, SQLCancelRequest, SQLExplainRequest
from engine.schemas.credentials import CredentialEnrollmentRequest, CredentialReference

__all__ = [
    "ProjectCreateRequest",
    "BackupCreateRequest",
    "ErrorResponse",
    "ProblemDetails",
    "TestDataGenerateRequest",
    "DataSourceTestRequest",
    "DataSourceCreateRequest",
    "DataSourceUpdateRequest",
    "SQLValidateRequest",
    "SQLCancelRequest",
    "SQLExplainRequest",
    "CredentialEnrollmentRequest",
    "CredentialReference",
]
