from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from engine.agent_contracts.types import ToolObservation


class ToolContractError(ValueError):
    """Raised when a tool call violates its declared runtime contract."""


class ToolRuntimeGateway:
    @staticmethod
    def validate_input(tool_name: str, input_model: type[BaseModel] | None, tool_input: dict[str, Any]) -> dict[str, Any]:
        if input_model is None:
            return dict(tool_input)
        try:
            parsed = input_model.model_validate(tool_input)
        except ValidationError as exc:
            raise ToolContractError(f"Input contract failed for tool `{tool_name}`: {exc}") from exc
        return parsed.model_dump(mode="json")

    @staticmethod
    def validate_observation_output(
        tool_name: str,
        output_model: type[BaseModel] | None,
        observation: ToolObservation,
    ) -> ToolObservation:
        if output_model is None or observation.status != "success":
            return observation
        try:
            output_model.model_validate(observation.output)
        except ValidationError as exc:
            raise ToolContractError(f"Output contract failed for tool `{tool_name}`: {exc}") from exc
        return observation
