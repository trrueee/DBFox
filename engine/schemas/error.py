from typing import Any
from pydantic import BaseModel, Field

class ErrorResponse(BaseModel):
    code: str
    message: str
    checks: list[dict[str, Any]] = Field(default_factory=list)


class ProblemDetails(BaseModel):
    """RFC 9457 response with DBFox correlation and machine-code extensions."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    request_id: str
    checks: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
