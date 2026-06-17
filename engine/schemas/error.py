from typing import Any
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    code: str
    message: str
    checks: list[dict[str, Any]] = []
