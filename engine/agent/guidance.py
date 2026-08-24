"""Static trusted capability guidance materialized per model Turn."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from engine.json_codec import canonical_dumps
from engine.tools.materialization import ToolMaterialization
from engine.tools.runtime.registry import ToolKey, ToolRegistry


MAX_CAPABILITY_GUIDANCE_CHARS = 8_000
_GUIDANCE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


@dataclass(frozen=True)
class CapabilityGuidanceSpec:
    id: str
    version: str
    instructions: str
    applies_to_resource_kinds: tuple[str, ...] = ()
    applies_to_artifact_types: tuple[str, ...] = ()
    tool_refs: tuple[ToolKey, ...] = ()

    def validate(self) -> None:
        if _GUIDANCE_ID.fullmatch(self.id) is None:
            raise ValueError("Capability guidance id must use lowercase namespace syntax")
        if not self.version.strip() or len(self.version) > 64:
            raise ValueError("Capability guidance version is invalid")
        if not self.instructions.strip() or len(self.instructions) > MAX_CAPABILITY_GUIDANCE_CHARS:
            raise ValueError("Capability guidance instructions are empty or exceed the bounded contract")
        if not (
            self.applies_to_resource_kinds
            or self.applies_to_artifact_types
            or self.tool_refs
        ):
            raise ValueError("Capability guidance must declare at least one activation selector")


@dataclass(frozen=True)
class CapabilityGuidanceContribution:
    spec: CapabilityGuidanceSpec
    owner_id: str
    package_digest: str | None = None


@dataclass(frozen=True)
class MaterializedCapabilityGuidance:
    id: str
    version: str
    owner_id: str
    instructions: str
    tool_names: tuple[tuple[str, str], ...]
    hash: str

    def prompt_section(self) -> str:
        tools = ""
        if self.tool_names:
            tools = "\nCapability function identities:\n" + "\n".join(
                f"- {local_name}: `{wire_name}`"
                for local_name, wire_name in self.tool_names
            )
        return (
            f"## Capability guidance: {self.owner_id}/{self.id}@{self.version}\n"
            f"{self.instructions.strip()}{tools}"
        )

    def identity(self) -> dict[str, str]:
        return {
            "owner_id": self.owner_id,
            "id": self.id,
            "version": self.version,
            "hash": self.hash,
        }


def materialize_capability_guidance(
    contributions: tuple[CapabilityGuidanceContribution, ...],
    *,
    resource_kinds: frozenset[str],
    artifact_types: frozenset[str],
    tools: ToolMaterialization,
    registry: ToolRegistry,
) -> tuple[MaterializedCapabilityGuidance, ...]:
    materialized_wire_names = {tool.name for tool in tools.tools}
    active: list[MaterializedCapabilityGuidance] = []
    for contribution in contributions:
        spec = contribution.spec
        resolved_tools_list: list[tuple[str, str]] = []
        for ref in spec.tool_refs:
            try:
                wire_name = registry.provider_name_for_key(ref)
            except KeyError:
                continue
            if wire_name in materialized_wire_names:
                resolved_tools_list.append((ref.local_name, wire_name))
        resolved_tools = tuple(resolved_tools_list)
        applies = bool(
            resource_kinds.intersection(spec.applies_to_resource_kinds)
            or artifact_types.intersection(spec.applies_to_artifact_types)
            or resolved_tools
        )
        if not applies:
            continue
        payload = {
            "owner_id": contribution.owner_id,
            "package_digest": contribution.package_digest,
            "id": spec.id,
            "version": spec.version,
            "instructions": spec.instructions,
            "tool_names": resolved_tools,
        }
        active.append(MaterializedCapabilityGuidance(
            id=spec.id,
            version=spec.version,
            owner_id=contribution.owner_id,
            instructions=spec.instructions,
            tool_names=resolved_tools,
            hash="sha256:" + hashlib.sha256(
                canonical_dumps(payload).encode("utf-8")
            ).hexdigest(),
        ))
    return tuple(sorted(active, key=lambda item: (item.owner_id, item.id, item.version)))
