from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import TYPE_CHECKING



from engine.tools.runtime.base import BaseTool, ControlCommand, ToolCapability

if TYPE_CHECKING:
    from engine.tools.runtime.attempt import ToolImplementationIdentity



RegisteredFunction = BaseTool | ControlCommand

_OWNER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_PROVIDER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

IN_PROCESS_CAPABILITIES: frozenset[ToolCapability] = frozenset(
    {
        "metadata_read",
        "metadata_write",
        "filesystem_read",
        "network",
    }
)


@dataclass(frozen=True, slots=True)
class ToolKey:
    """Canonical runtime identity independent of provider wire encoding."""

    owner_id: str | None
    local_name: str


def provider_tool_name(owner_id: str | None, local_name: str) -> str:
    """Derive one stable provider-safe function name from a canonical ToolKey."""

    if owner_id is None:
        return local_name
    owner_slug = re.sub(r"[^a-z0-9]+", "_", owner_id).strip("_")[:20]
    owner_hash = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()[:8]
    prefix = f"{owner_slug}_{owner_hash}__"
    available = 64 - len(prefix)
    if len(local_name) <= available:
        return prefix + local_name
    local_hash = hashlib.sha256(local_name.encode("utf-8")).hexdigest()[:8]
    return prefix + local_name[: available - 10] + "__" + local_hash


class ToolRegistry:
    def __init__(self, *, available_backends: frozenset[str] | None = None) -> None:
        self._tools: dict[ToolKey, RegisteredFunction] = {}
        self._wire_names: dict[ToolKey, str] = {}
        self._keys_by_wire_name: dict[str, ToolKey] = {}
        self._keys_by_object_id: dict[int, ToolKey] = {}
        self._package_digests: dict[ToolKey, str] = {}
        self._frozen = False
        self._available_backends = available_backends or frozenset({"in_process"})

    @property
    def frozen(self) -> bool:
        return self._frozen

    def register(
        self,
        tool: RegisteredFunction,
        *,
        owner: str | None = None,
        package_digest: str | None = None,
        provider_name: str | None = None,
    ) -> "ToolRegistry":
        if self._frozen:
            raise RuntimeError("Tool Registry is frozen; registration is rejected.")
        if owner is not None and not _OWNER_ID_PATTERN.fullmatch(owner):
            raise ValueError(
                "Extension owner ID must use lowercase namespace syntax "
                f"(for example 'dbfox.data'), got: {owner!r}"
            )
        key = ToolKey(owner_id=owner, local_name=tool.name)
        if key in self._tools:
            raise ValueError(f"Tool {key!r} is already registered.")
        wire_name = provider_name or provider_tool_name(owner, tool.name)
        if _PROVIDER_NAME_PATTERN.fullmatch(wire_name) is None:
            raise ValueError(
                f"Provider Tool name {wire_name!r} must match {_PROVIDER_NAME_PATTERN.pattern}"
            )
        conflicting_key = self._keys_by_wire_name.get(wire_name)
        if conflicting_key is not None:
            raise ValueError(
                f"Provider Tool name {wire_name!r} for {key!r} conflicts with {conflicting_key!r}."
            )
        self._validate_execution_boundary(tool)
        self._tools[key] = tool
        self._wire_names[key] = wire_name
        self._keys_by_wire_name[wire_name] = key
        self._keys_by_object_id[id(tool)] = key
        if package_digest is not None:
            self._package_digests[key] = package_digest
        return self

    def freeze(self) -> "ToolRegistry":
        self._frozen = True
        return self

    def owner_of(self, name: str) -> str | None:
        key = self._keys_by_wire_name.get(name)
        return key.owner_id if key is not None else None

    def package_digest_of(self, name: str) -> str | None:
        key = self._keys_by_wire_name.get(name)
        return self._package_digests.get(key) if key is not None else None

    def key_of(self, tool: RegisteredFunction) -> ToolKey:
        key = self._keys_by_object_id.get(id(tool))
        if key is None:
            raise KeyError("Tool instance is not registered")
        return key

    def provider_name_of(self, tool: RegisteredFunction) -> str:
        return self._wire_names[self.key_of(tool)]

    def provider_name_for_key(self, key: ToolKey) -> str:
        try:
            return self._wire_names[key]
        except KeyError as exc:
            raise KeyError(f"Unknown Tool key {key!r}") from exc

    def owner_of_tool(self, tool: RegisteredFunction) -> str | None:
        return self.key_of(tool).owner_id

    def package_digest_of_tool(self, tool: RegisteredFunction) -> str | None:
        return self._package_digests.get(self.key_of(tool))

    def implementation_identity_of(self, name: str) -> ToolImplementationIdentity | None:
        owner = self.owner_of(name)
        if owner is None:
            return None
        from engine.tools.runtime.attempt import ToolImplementationIdentity

        return ToolImplementationIdentity(
            owner_id=owner,
            package_digest=self.package_digest_of(name),
        )


    def tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys_by_wire_name))

    def get(self, name: str) -> RegisteredFunction | None:
        key = self._keys_by_wire_name.get(name)
        return self._tools.get(key) if key is not None else None

    def get_by_key(self, key: ToolKey) -> RegisteredFunction | None:
        return self._tools.get(key)

    def require_key(self, key: ToolKey) -> RegisteredFunction:
        tool = self.get_by_key(key)
        if tool is None:
            raise KeyError(f"Unknown Tool key {key!r}")
        return tool

    def tool_keys(self) -> tuple[ToolKey, ...]:
        return tuple(sorted(self._tools, key=lambda key: (key.owner_id or "", key.local_name)))

    def require(self, name: str) -> RegisteredFunction:
        tool = self.get(name)
        if tool is None:
            available = ", ".join(self.tool_names()) or "<none>"
            raise KeyError(f"Unknown Agent tool `{name}`. Available tools: {available}")
        return tool

    def list_tools(self) -> list[RegisteredFunction]:
        return [self.require(name) for name in self.tool_names()]

    def list_specs(self):
        return [tool.spec for tool in self.list_tools()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._keys_by_wire_name

    def _validate_execution_boundary(self, tool: RegisteredFunction) -> None:
        execution = tool.execution
        capabilities = set(execution.capabilities)
        if execution.backend not in self._available_backends:
            raise ValueError(
                f"Tool '{tool.name}' requires unavailable execution backend "
                f"'{execution.backend}'."
            )
        if execution.backend == "in_process" and not capabilities <= IN_PROCESS_CAPABILITIES:
            forbidden = ", ".join(sorted(capabilities - IN_PROCESS_CAPABILITIES))
            raise ValueError(
                f"Tool '{tool.name}' requests capabilities that require an isolated process: {forbidden}"
            )
