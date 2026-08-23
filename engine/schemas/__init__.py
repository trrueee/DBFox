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
from engine.schemas.error import ErrorResponse, ProblemDetails
from engine.schemas.credentials import CredentialEnrollmentRequest, CredentialReference

__all__ = [
    "ProjectCreateRequest",
    "ErrorResponse",
    "ProblemDetails",
    "CredentialEnrollmentRequest",
    "CredentialReference",
]
