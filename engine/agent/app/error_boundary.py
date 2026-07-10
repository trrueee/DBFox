"""Strict public error boundary for Agent execution.

Provider exceptions can contain request URLs, authorization fragments, or
configuration representations.  They must never be copied into agent state,
events, HTTP payloads, SSE frames, or logs.
"""
from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from typing import Literal

from engine.errors import DBFoxError
from engine.llm.config import LlmConfigurationError


AgentOperation = Literal["llm_test", "run", "resume", "cancel", "approval"]


@dataclass(frozen=True)
class PublicAgentFailure:
    code: str
    message: str
    status_code: int

    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


_PUBLIC_FAILURES: dict[AgentOperation, tuple[str, str]] = {
    "llm_test": (
        "LLM_TEST_FAILED",
        "The LLM connection test could not be completed.",
    ),
    "run": (
        "AGENT_RUNTIME_ERROR",
        "The agent run could not be completed.",
    ),
    "resume": (
        "AGENT_RESUME_ERROR",
        "The agent run could not be resumed.",
    ),
    "cancel": (
        "AGENT_CANCEL_ERROR",
        "The agent run could not be cancelled.",
    ),
    "approval": (
        "APPROVAL_RESOLVE_ERROR",
        "The approval decision could not be applied.",
    ),
}


def public_agent_failure(exc: Exception, *, operation: AgentOperation) -> PublicAgentFailure:
    """Map any runtime exception to a stable, secret-free public response."""
    code, message = _PUBLIC_FAILURES[operation]
    status_code = 400 if isinstance(exc, (DBFoxError, LlmConfigurationError)) else 500
    return PublicAgentFailure(code=code, message=message, status_code=status_code)


def safe_agent_log(
    logger: Logger,
    *,
    operation: AgentOperation,
    exc: Exception,
    run_id: str | None = None,
) -> None:
    """Record only fixed context and exception type, never exception text/traceback."""
    suffix = f" run_id={run_id}" if run_id else ""
    logger.error("Agent %s failed (%s)%s", operation, type(exc).__name__, suffix)
