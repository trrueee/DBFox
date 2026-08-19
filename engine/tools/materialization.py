"""Deterministic per-Turn tool materialization."""

from __future__ import annotations

import hashlib
from typing import Any

from openai import pydantic_function_tool
from pydantic import BaseModel, ConfigDict, Field

from engine.json_codec import canonical_dumps
from engine.tools.runtime.base import BaseTool, ControlCommand, ToolRecoveryPolicy
from engine.tools.runtime.registry import ToolRegistry


class ToolVersionMismatch(RuntimeError):
    """A durable call no longer matches the installed tool contract."""


class MaterializedTool(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    declared_version: str = Field(
        description="Domain semantic version used for historical interpretation."
    )
    contract_hash: str = Field(
        description="Content-addressed identifier of the complete executable tool contract."
    )
    group: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    policy: dict[str, Any]
    execution: dict[str, Any]
    semantics: dict[str, Any]
    presentation: dict[str, Any]
    recovery_policy: ToolRecoveryPolicy
    kind: str

    def provider_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
            "strict": True,
        }


class ToolMaterialization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tools: tuple[MaterializedTool, ...] = ()
    hash: str

    def provider_schemas(self) -> list[dict[str, Any]]:
        return [tool.provider_schema() for tool in self.tools]

    def require(self, name: str) -> MaterializedTool:
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise KeyError(f"Tool is not materialized for this Turn: {name}")


def materialize_tools(
    registry: ToolRegistry,
    *,
    allowed_groups: set[str] | None = None,
    allowed_names: set[str] | None = None,
    execution_mode: str,
    available_resource_kinds: set[str] | frozenset[str] | None = None,
) -> ToolMaterialization:
    materialized: list[MaterializedTool] = []
    for tool in registry.list_tools():
        spec = tool.spec
        if not spec.policy.visible_to_model:
            continue
        if allowed_groups is not None and spec.group not in allowed_groups:
            continue
        if allowed_names is not None and spec.name not in allowed_names:
            continue
        allowed_modes = set(spec.policy.allowed_execution_modes)
        if allowed_modes and execution_mode not in allowed_modes:
            continue
        if available_resource_kinds is not None:
            required = set(spec.execution.required_resource_kinds)
            if not required.issubset(available_resource_kinds):
                continue
        materialized.append(_materialize_tool(tool))

    materialized.sort(key=lambda value: value.name)
    payload = [tool.model_dump(mode="json") for tool in materialized]
    digest = _canonical_digest(payload)
    return ToolMaterialization(tools=materialized, hash=digest)


def require_current_tool(
    registry: ToolRegistry,
    materialization: ToolMaterialization,
    *,
    name: str,
    contract_hash: str,
) -> Any:
    try:
        frozen = materialization.require(name)
        current = registry.require(name)
    except KeyError as exc:
        raise ToolVersionMismatch(
            f"Tool {name} is not available in both the frozen and current registries"
        ) from exc
    current_contract = _materialize_tool(current)
    if (
        contract_hash != frozen.contract_hash
        or current_contract.contract_hash != frozen.contract_hash
    ):
        raise ToolVersionMismatch(
            f"Tool {name} contract {contract_hash!r} cannot run against "
            f"frozen={frozen.contract_hash!r}, current={current_contract.contract_hash!r}"
        )
    return current


def require_reconciliation_tool(
    registry: ToolRegistry,
    materialization: ToolMaterialization,
    *,
    name: str,
    contract_hash: str,
) -> Any:
    """Resolve only the read-only reconciler for an already-attempted call.

    A current policy or presentation change must not hide the outcome of an
    external action that may already have completed. This path never authorizes
    replay: it only verifies that the original call used the frozen contract and
    that both frozen and current tools retain the explicit reconciliation
    contract.
    """

    try:
        frozen = materialization.require(name)
        current = registry.require(name)
    except KeyError as exc:
        raise ToolVersionMismatch(
            f"Tool {name} is not available for reconciliation"
        ) from exc
    if (
        contract_hash != frozen.contract_hash
        or frozen.recovery_policy is not ToolRecoveryPolicy.RECONCILE
        or current.execution.recovery is not ToolRecoveryPolicy.RECONCILE
    ):
        raise ToolVersionMismatch(
            f"Tool {name} no longer satisfies its frozen reconciliation contract"
        )
    return current


def _materialize_tool(
    tool: BaseTool[Any, Any] | ControlCommand[Any, Any],
) -> MaterializedTool:
    spec = tool.spec
    input_schema = _strict_input_schema(spec.input_model)
    output_schema = spec.output_model.model_json_schema()
    policy = spec.policy.model_dump(mode="json")
    execution = spec.execution.model_dump(mode="json")
    semantics = spec.semantics.model_dump(mode="json")
    presentation = spec.presentation.model_dump(mode="json")
    contract_payload = {
        "name": spec.name,
        "declared_version": spec.version,
        "group": spec.group,
        "description": spec.description,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "policy": policy,
        "execution": execution,
        "semantics": semantics,
        "presentation": presentation,
        "kind": spec.kind,
    }
    return MaterializedTool(
        name=spec.name,
        declared_version=str(spec.version),
        contract_hash=f"sha256:{_canonical_digest(contract_payload)}",
        group=spec.group,
        description=spec.description,
        input_schema=input_schema,
        output_schema=output_schema,
        policy=policy,
        execution=execution,
        semantics=semantics,
        presentation=presentation,
        recovery_policy=spec.execution.recovery,
        kind=spec.kind,
    )


def current_tool_contract_hash(
    tool: BaseTool[Any, Any] | ControlCommand[Any, Any],
) -> str:
    """Return the current executable contract hash for a registered tool."""

    return _materialize_tool(tool).contract_hash


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()


def _strict_input_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Generate OpenAI strict JSON Schema through the SDK's public helper."""

    parameters = pydantic_function_tool(model)["function"].get("parameters")
    if not isinstance(parameters, dict):
        raise TypeError("OpenAI SDK did not produce a function parameter schema")
    return parameters
