"""Deterministic per-Turn tool materialization."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engine.tools.runtime.registry import ToolRegistry


class ToolRecoveryPolicy(StrEnum):
    RETRY_SAFE = "retry_safe"
    RECONCILE = "reconcile"
    NEVER_RETRY = "never_retry"
    PROVIDER_OWNED = "provider_owned"


class MaterializedTool(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    version: str
    group: str
    description: str
    input_schema: dict[str, Any]
    policy: dict[str, Any]
    execution: dict[str, Any]
    recovery_policy: ToolRecoveryPolicy

    def provider_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolMaterialization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tools: list[MaterializedTool] = Field(default_factory=list)
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
    execution_mode: str,
) -> ToolMaterialization:
    materialized: list[MaterializedTool] = []
    for tool in registry.list_tools():
        spec = tool.spec
        if not spec.policy.visible_to_model:
            continue
        if allowed_groups is not None and spec.group not in allowed_groups:
            continue
        allowed_modes = set(spec.policy.allowed_execution_modes)
        if allowed_modes and execution_mode not in allowed_modes:
            continue
        recovery = _recovery_policy(tool)
        materialized.append(
            MaterializedTool(
                name=spec.name,
                version=str(spec.metadata.get("version", "1") if spec.metadata else "1"),
                group=spec.group,
                description=spec.description,
                input_schema=spec.input_schema,
                policy=spec.policy.model_dump(mode="json"),
                execution=spec.execution.model_dump(mode="json"),
                recovery_policy=recovery,
            )
        )

    materialized.sort(key=lambda value: value.name)
    payload = [tool.model_dump(mode="json") for tool in materialized]
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return ToolMaterialization(tools=materialized, hash=digest)


def _recovery_policy(tool: Any) -> ToolRecoveryPolicy:
    configured = (tool.spec.metadata or {}).get("recovery_policy")
    if configured:
        return ToolRecoveryPolicy(str(configured))
    if tool.spec.policy.side_effect in {"none", "read"} and tool.spec.execution.idempotent:
        return ToolRecoveryPolicy.RETRY_SAFE
    return ToolRecoveryPolicy.NEVER_RETRY
