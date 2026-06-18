from __future__ import annotations

import time
from typing import Any

from pydantic import ValidationError

from engine.agent_core.types import ToolObservation
from engine.tools.runtime.context import ToolRunContext
from engine.tools.runtime.registry import ToolRegistry


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
    ) -> ToolObservation:
        tool = self.registry.require(tool_name)
        start = time.perf_counter()
        try:
            parsed_input = tool.input_model.model_validate(raw_input)
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
                ),
            )
            parsed_output = tool.output_model.model_validate(output)
        except ValidationError as exc:
            return self._failed(tool_name, raw_input, "Output contract failed", exc, start)
        except Exception as exc:
            return self._failed(tool_name, raw_input, "Tool execution failed", exc, start)

        return ToolObservation(
            name=tool_name,
            status="success",
            input=dict(raw_input),
            output=parsed_output.model_dump(mode="json"),
            error=None,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    @staticmethod
    def _failed(
        tool_name: str,
        raw_input: dict[str, Any],
        message: str,
        exc: Exception,
        start: float,
    ) -> ToolObservation:
        return ToolObservation(
            name=tool_name,
            status="failed",
            input=dict(raw_input),
            output=None,
            error=f"{message} for tool `{tool_name}`: {exc}",
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
