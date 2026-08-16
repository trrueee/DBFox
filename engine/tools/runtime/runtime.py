from __future__ import annotations

import logging
import time
from typing import Any, Callable, Final, Literal

from pydantic import JsonValue, TypeAdapter, ValidationError

from engine.errors import DBFoxError, ToolInputError
from engine.tools.runtime.result import ToolOutcome, ToolReconciliation, ToolResult
from engine.app.safe_errors import (
    SafeLogOperation,
    fixed_error_detail,
    log_unexpected_exception,
)
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.tools.runtime.context import ToolRunContext
from engine.tools.runtime.registry import ToolRegistry
from engine.tools.runtime.base import BaseTool

logger = logging.getLogger("dbfox.tools.runtime")
_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])
_MAX_TOOL_INPUT_ERROR_CHARS: Final[int] = 1_024

ToolFailureCode = Literal[
    "TOOL_INPUT_CONTRACT_FAILED",
    "TOOL_OUTPUT_CONTRACT_FAILED",
    "TOOL_EXECUTION_FAILED",
]

_TOOL_FAILURE_MESSAGES: Final[dict[ToolFailureCode, str]] = {
    "TOOL_INPUT_CONTRACT_FAILED": "Input contract failed.",
    "TOOL_OUTPUT_CONTRACT_FAILED": "Output contract failed.",
    "TOOL_EXECUTION_FAILED": "Tool execution failed.",
}

_TOOL_FAILURE_OPERATIONS: Final[dict[ToolFailureCode, SafeLogOperation]] = {
    "TOOL_INPUT_CONTRACT_FAILED": SafeLogOperation.TOOL_RUNTIME_INPUT_CONTRACT_FAILED,
    "TOOL_OUTPUT_CONTRACT_FAILED": SafeLogOperation.TOOL_RUNTIME_OUTPUT_CONTRACT_FAILED,
    "TOOL_EXECUTION_FAILED": SafeLogOperation.TOOL_RUNTIME_EXECUTION_FAILED,
}


class ToolRuntime:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def invoke(
        self,
        *,
        tool_name: str,
        raw_input: dict[str, Any],
        request: Any | None,
        db: Any | None,
        idempotency_key: str,
        cancellation_probe: Callable[[], bool] | None = None,
        deadline: float | None = None,
        execution_authority: Any | None = None,
        scope_refs: tuple[ResourceScopeRef, ...] | None = None,
        resources: dict[str, Any] | None = None,
    ) -> ToolResult:
        tool = self.registry.require(tool_name)
        if not isinstance(tool, BaseTool):
            raise TypeError(
                f"{tool_name} is a Runtime control command, not an executable tool"
            )
        start = time.perf_counter()

        try:
            parsed_input = tool.input_model.model_validate(raw_input)
        except ValidationError as exc:
            return self._failed(
                tool_name,
                raw_input,
                code="TOOL_INPUT_CONTRACT_FAILED",
                exc=exc,
                start=start,
            )

        if cancellation_probe and cancellation_probe():
            return ToolResult(
                name=tool_name, status="failed", input=dict(raw_input),
                error="Tool execution was cancelled.", error_code="TOOL_CANCELLED",
                latency_ms=int((time.perf_counter() - start) * 1_000),
            )
        if deadline is not None and time.monotonic() >= deadline:
            return ToolResult(
                name=tool_name, status="failed", input=dict(raw_input),
                error="Tool execution exceeded its deadline.", error_code="TOOL_TIMEOUT",
                latency_ms=int((time.perf_counter() - start) * 1_000),
            )
        try:
            outcome = tool.run(
                parsed_input,
                ToolRunContext.for_invocation(
                    request=request,
                    db=db,
                    raw_input=raw_input,
                    cancellation_probe=cancellation_probe,
                    deadline=deadline,
                    execution_authority=execution_authority,
                    scope_refs=scope_refs,
                    resources=resources,
                    idempotency_key=idempotency_key,
                ),
            )
            if isinstance(outcome, ToolOutcome):
                output = outcome.output
                artifact_drafts = list(outcome.artifacts)
            else:
                output = outcome
                artifact_drafts = []
            if cancellation_probe and cancellation_probe():
                return ToolResult(
                    name=tool_name, status="failed", input=dict(raw_input),
                    error="Tool execution was cancelled.", error_code="TOOL_CANCELLED",
                    latency_ms=int((time.perf_counter() - start) * 1_000),
                )
            if deadline is not None and time.monotonic() >= deadline:
                return ToolResult(
                    name=tool_name, status="failed", input=dict(raw_input),
                    error="Tool execution exceeded its deadline.", error_code="TOOL_TIMEOUT",
                    latency_ms=int((time.perf_counter() - start) * 1_000),
                )
        except ToolInputError as exc:
            safe_message = exc.message.strip()
            if len(safe_message) > _MAX_TOOL_INPUT_ERROR_CHARS:
                safe_message = safe_message[:_MAX_TOOL_INPUT_ERROR_CHARS] + "…"
            if not safe_message:
                safe_message = fixed_error_detail(exc.code)["message"]
            logger.info("%s rejected invalid input code=%s", tool_name, exc.code)
            return ToolResult(
                name=tool_name,
                status="failed",
                input=dict(raw_input),
                output={
                    "status": "failed",
                    "error_code": exc.code,
                    "safe_message": safe_message,
                },
                error=safe_message,
                error_code=exc.code,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        except DBFoxError as exc:
            # DBFoxError.message is internal diagnostic text unless an explicit
            # boundary type (ToolInputError above) declares otherwise.  Only a
            # registered fixed code may cross into Tool/Observation/Provider
            # output; unknown codes collapse to the generic catalog member.
            logger.info("%s failed with domain error code=%s", tool_name, exc.code)
            detail = fixed_error_detail(exc.code)
            return ToolResult(
                name=tool_name,
                status="failed",
                input=dict(raw_input),
                output={
                    "status": "failed",
                    "error_code": detail["code"],
                    "safe_message": detail["message"],
                },
                error=detail["message"],
                error_code=detail["code"],
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:
            return self._failed(
                tool_name,
                raw_input,
                code="TOOL_EXECUTION_FAILED",
                exc=exc,
                start=start,
            )
        try:
            parsed_output_model = tool.output_model.model_validate(output)
            parsed_output = _JSON_OBJECT.validate_python(
                parsed_output_model.model_dump(mode="json", by_alias=True)
            )
        except ValidationError as exc:
            return self._failed(
                tool_name,
                raw_input,
                code="TOOL_OUTPUT_CONTRACT_FAILED",
                exc=exc,
                start=start,
            )

        elapsed = int((time.perf_counter() - start) * 1000)
        logger.info("%s OK (%dms)", tool_name, elapsed)
        return ToolResult(
            name=tool_name,
            status="success",
            input=dict(raw_input),
            output=parsed_output,
            artifact_drafts=artifact_drafts,
            error=None,
            error_code=None,
            latency_ms=elapsed,
        )

    def reconcile(
        self,
        *,
        tool_name: str,
        raw_input: dict[str, Any],
        request: Any | None,
        db: Any | None,
        idempotency_key: str,
        cancellation_probe: Callable[[], bool] | None = None,
        deadline: float | None = None,
        execution_authority: Any | None = None,
        scope_refs: tuple[ResourceScopeRef, ...] | None = None,
        resources: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Resolve an interrupted action by its stable invocation key."""

        tool = self.registry.require(tool_name)
        if not isinstance(tool, BaseTool):
            raise TypeError(
                f"{tool_name} is a Runtime control command, not an executable tool"
            )
        start = time.perf_counter()
        try:
            parsed_input = tool.input_model.model_validate(raw_input)
        except ValidationError as exc:
            return self._reconciliation_unknown(
                tool_name,
                raw_input,
                exc=exc,
                start=start,
            )
        try:
            reconciliation = ToolReconciliation.model_validate(
                tool.reconcile(
                    parsed_input,
                    ToolRunContext.for_invocation(
                        request=request,
                        db=db,
                        raw_input=raw_input,
                        cancellation_probe=cancellation_probe,
                        deadline=deadline,
                        execution_authority=execution_authority,
                        scope_refs=scope_refs,
                        resources=resources,
                        idempotency_key=idempotency_key,
                    ),
                )
            )
        except Exception as exc:
            return self._reconciliation_unknown(
                tool_name,
                raw_input,
                exc=exc,
                start=start,
            )

        elapsed = int((time.perf_counter() - start) * 1_000)
        if reconciliation.status == "succeeded":
            try:
                output_model = tool.output_model.model_validate(
                    reconciliation.output or {}
                )
                output = _JSON_OBJECT.validate_python(
                    output_model.model_dump(mode="json", by_alias=True)
                )
            except ValidationError as exc:
                return self._reconciliation_unknown(
                    tool_name,
                    raw_input,
                    exc=exc,
                    start=start,
                )
            return ToolResult(
                name=tool_name,
                status="success",
                input=dict(raw_input),
                output=output,
                latency_ms=elapsed,
            )
        if reconciliation.status == "not_applied":
            return ToolResult(
                name=tool_name,
                status="failed",
                input=dict(raw_input),
                error=reconciliation.error or "The interrupted action was not applied.",
                error_code="TOOL_RECONCILIATION_NOT_APPLIED",
                latency_ms=elapsed,
            )
        if reconciliation.status == "unknown":
            return ToolResult(
                name=tool_name,
                status="failed",
                input=dict(raw_input),
                error=reconciliation.error or "The interrupted action outcome is unknown.",
                error_code="TOOL_OUTCOME_UNKNOWN",
                latency_ms=elapsed,
            )
        return ToolResult(
            name=tool_name,
            status="failed",
            input=dict(raw_input),
            error=reconciliation.error or "The interrupted action failed.",
            error_code=reconciliation.error_code or "TOOL_RECONCILIATION_FAILED",
            latency_ms=elapsed,
        )

    @staticmethod
    def _reconciliation_unknown(
        tool_name: str,
        raw_input: dict[str, Any],
        *,
        exc: Exception,
        start: float,
    ) -> ToolResult:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.TOOL_RUNTIME_EXECUTION_FAILED,
            exc=exc,
        )
        return ToolResult(
            name=tool_name,
            status="failed",
            input=dict(raw_input),
            error="The interrupted action could not be reconciled.",
            error_code="TOOL_OUTCOME_UNKNOWN",
            latency_ms=int((time.perf_counter() - start) * 1_000),
        )

    @staticmethod
    def _failed(
        tool_name: str,
        raw_input: dict[str, Any],
        *,
        code: ToolFailureCode,
        exc: Exception,
        start: float,
    ) -> ToolResult:
        log_unexpected_exception(
            logger,
            operation=_TOOL_FAILURE_OPERATIONS[code],
            exc=exc,
        )
        return ToolResult(
            name=tool_name,
            status="failed",
            input=dict(raw_input),
            output={
                "status": "failed",
                "error_code": code,
                "error_type": type(exc).__name__,
            },
            error=_TOOL_FAILURE_MESSAGES[code],
            error_code=code,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
