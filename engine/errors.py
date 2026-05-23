class DataBoxError(Exception):
    """Base error for all DataBox related issues."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class DataSourceConnectionError(DataBoxError):
    """Raised when failing to connect to the database."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONNECTION_FAILED")


class GuardrailValidationError(DataBoxError):
    """Raised when a SQL query fails safety Guardrail checks."""

    def __init__(self, message: str, checks: list[dict[str, str]] | None = None) -> None:
        super().__init__(message, code="GUARDRAIL_BLOCKED")
        self.checks = checks or []


class SQLExecutionError(DataBoxError):
    """Raised when execution of SQL fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="SQL_EXECUTION_FAILED")


class SQLQueryTimeoutError(DataBoxError):
    """Raised when a query exceeds the server-side timeout guard."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="SQL_QUERY_TIMEOUT")


class SQLQueryCancelledError(DataBoxError):
    """Raised when a running query is cancelled by the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="SQL_QUERY_CANCELLED")


class AIServiceError(DataBoxError):
    """Raised when the AI Text-to-SQL engine fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="AI_TRANSLATION_FAILED")
