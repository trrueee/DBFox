from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from pydantic import ValidationError

from engine.agent_core.types import ToolObservation
from engine.tools.runtime.context import ToolRunContext
from engine.tools.runtime.registry import ToolRegistry

logger = logging.getLogger("dbfox.tools.runtime")


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
        emit_answer_delta: Callable[[str], None] | None = None,
    ) -> ToolObservation:
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
            return self._failed(tool_name, raw_input, "Input contract failed", exc, start)

        projection = {
            key: state.get(key)
            for key in tool.state.consumes
            if key in state
        }
        try:
            output = tool.run(
                parsed_input,
                ToolRunContext.from_projection(
                    state=projection,
                    request=request,
                    db=db,
                    read_only=tool.policy.side_effect not in {"write", "destructive"},
                    raw_input=coerced_input,
                    emit_answer_delta=emit_answer_delta,
                ),
            )
            parsed_output = tool.output_model.model_validate(output)
        except ValidationError as exc:
            return self._failed(tool_name, raw_input, "Output contract failed", exc, start)
        except Exception as exc:
            return self._failed(tool_name, raw_input, "Tool execution failed", exc, start)

        elapsed = int((time.perf_counter() - start) * 1000)
        logger.info("%s OK (%dms)", tool_name, elapsed)
        return ToolObservation(
            name=tool_name,
            status="success",
            input=dict(raw_input),
            output=parsed_output.model_dump(mode="json"),
            error=None,
            latency_ms=elapsed,
        )

    @staticmethod
    def _failed(
        tool_name: str,
        raw_input: dict[str, Any],
        message: str,
        exc: Exception,
        start: float,
    ) -> ToolObservation:
        logger.error("%s FAILED (%dms): %s — %s", tool_name, int((time.perf_counter() - start) * 1000), message, exc)
        return ToolObservation(
            name=tool_name,
            status="failed",
            input=dict(raw_input),
            output=None,
            error=f"{message} for tool `{tool_name}`: {exc}",
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
