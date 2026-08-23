"""Domain exceptions exposed by the DBFox engine."""

from __future__ import annotations


class DBFoxError(Exception):
    """Base exception carrying a stable public error code."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ToolInputError(DBFoxError):
    """Invalid model-provided tool input safe to expose to the client."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="TOOL_INPUT_ERROR")


class NotFoundError(DBFoxError):
    def __init__(self, message: str, code: str = "NOT_FOUND") -> None:
        super().__init__(message, code=code)
