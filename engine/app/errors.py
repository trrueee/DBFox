from __future__ import annotations

from logging import Logger
from typing import Any, Literal

from engine.policy.error_sanitizer import sanitize_error_message


class PublicErrorService:
    def public_message(self, exc_or_message: Exception | str) -> str:
        return sanitize_error_message(str(exc_or_message))

    def public_error(self, code: str, exc_or_message: Exception | str) -> dict[str, Any]:
        return {
            "code": code,
            "message": self.public_message(exc_or_message),
        }


public_error_service = PublicErrorService()


def public_message(exc_or_message: Exception | str) -> str:
    return public_error_service.public_message(exc_or_message)


def public_error(code: str, exc_or_message: Exception | str) -> dict[str, Any]:
    return public_error_service.public_error(code, exc_or_message)


def safe_error_detail(code: str, message: str) -> dict[str, str]:
    """Build a public error detail from an explicitly fixed message only.

    This boundary is for catch-all exception handlers. It intentionally does
    not accept an exception object, because arbitrary exception text may carry
    credentials, endpoint URLs, or query data.
    """
    return {"code": code, "message": message}


def log_unexpected_exception(
    logger: Logger,
    *,
    operation: str,
    exc: Exception,
    level: Literal["warning", "error"] = "error",
) -> None:
    """Log stable context and exception class without rendering exception text."""
    log = logger.warning if level == "warning" else logger.error
    log("%s failed (%s)", operation, type(exc).__name__)
