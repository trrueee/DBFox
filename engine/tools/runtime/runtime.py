from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Final, Literal

from pydantic import ValidationError

from engine.tools.runtime.result import ToolResult
from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.tools.runtime.context import ToolRunContext
from engine.tools.runtime.registry import ToolRegistry

logger = logging.getLogger("dbfox.tools.runtime")

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
        state: dict[str, Any],
        request: Any | None,
        db: Any | None,
        cancellation_probe: Callable[[], bool] | None = None,
        deadline: float | None = None,
    ) -> ToolResult:
        tool = self.registry.require(tool_name)
        start = time.perf_counter()

        # Auto-coerce JSON strings → native types.  LLMs frequently pass
        # lists / dicts as JSON-encoded strings (e.g. columns='["a","b"]'),
        # which causes Pydantic validation to reject valid intent.
        coerced_input = dict(raw_input)
        for key, value in coerced_input.items():
            if isinstance(value, str) and len(value) >= 2:
                stripped = value.strip()
                if (stripped.startswith("[") and stripped.endswith("]")) or \
                   (stripped.startswith("{") and stripped.endswith("}")):
                    try:
                        coerced_input[key] = json.loads(stripped)
                    except (json.JSONDecodeError, ValueError):
                        pass  # not valid JSON, keep original string

        try:
            parsed_input = tool.input_model.model_validate(coerced_input)
        except ValidationError as exc:
            return self._failed(
                tool_name,
                raw_input,
                code="TOOL_INPUT_CONTRACT_FAILED",
                exc=exc,
                start=start,
            )

        projection = {
            key: state.get(key)
            for key in tool.state.consumes
            if key in state
        }
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
            output = tool.run(
                parsed_input,
                ToolRunContext.from_projection(
                    state=projection,
                    request=request,
                    db=db,
                    read_only=tool.policy.side_effect not in {"write", "destructive"},
                    raw_input=coerced_input,
                    cancellation_probe=cancellation_probe,
                    deadline=deadline,
                ),
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
            parsed_output = tool.output_model.model_validate(output)
        except ValidationError as exc:
            return self._failed(
                tool_name,
                raw_input,
                code="TOOL_OUTPUT_CONTRACT_FAILED",
                exc=exc,
                start=start,
            )
        except Exception as exc:
            return self._failed(
                tool_name,
                raw_input,
                code="TOOL_EXECUTION_FAILED",
                exc=exc,
                start=start,
            )

        elapsed = int((time.perf_counter() - start) * 1000)
        logger.info("%s OK (%dms)", tool_name, elapsed)
        return ToolResult(
            name=tool_name,
            status="success",
            input=dict(raw_input),
            output=parsed_output.model_dump(mode="json"),
            error=None,
            error_code=None,
            latency_ms=elapsed,
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
