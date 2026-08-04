"""Domain exceptions exposed by the DBFox engine."""

from __future__ import annotations


class DBFoxError(Exception):
    """Base exception carrying a stable public error code."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class DataSourceConnectionError(DBFoxError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONNECTION_FAILED")


class DataSourceCredentialUnavailableError(DataSourceConnectionError):
    """A datasource credential reference cannot currently yield its secret."""


class DataSourceSshConnectionError(DataSourceConnectionError):
    """The configured SSH transport failed before the database connection."""


class DataSourceTlsConnectionError(DataSourceConnectionError):
    """TLS configuration or negotiation failed at the connectivity boundary."""


class GuardrailValidationError(DBFoxError):
    def __init__(
        self,
        message: str,
        checks: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message, code="GUARDRAIL_BLOCKED")
        self.checks = checks or []


class SQLExecutionError(DBFoxError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="SQL_EXECUTION_FAILED")


class SQLQueryTimeoutError(DBFoxError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="SQL_QUERY_TIMEOUT")


class SQLQueryCancelledError(DBFoxError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="SQL_QUERY_CANCELLED")


class AIServiceError(DBFoxError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="AI_TRANSLATION_FAILED")


class ToolInputError(DBFoxError):
    """Invalid model-provided tool input safe to expose to the client."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="TOOL_INPUT_ERROR")


class NotFoundError(DBFoxError):
    def __init__(self, message: str, code: str = "NOT_FOUND") -> None:
        super().__init__(message, code=code)


class BackupSourceMismatchError(DBFoxError):
    def __init__(self) -> None:
        super().__init__(
            "Backup source no longer matches this datasource.",
            code="BACKUP_SOURCE_MISMATCH",
        )


class ValidationException(DBFoxError):
    def __init__(
        self,
        message: str,
        checks: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message, code="VALIDATION_FAILED")
        self.checks = checks or []
