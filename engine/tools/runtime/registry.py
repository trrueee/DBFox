from __future__ import annotations

from engine.tools.runtime.base import BaseTool, ControlCommand


RegisteredFunction = BaseTool | ControlCommand


IN_PROCESS_CAPABILITIES = frozenset({"metadata_read", "metadata_write", "database_read"})


class ToolRegistry:
    def __init__(self, *, available_backends: frozenset[str] | None = None) -> None:
        self._tools: dict[str, RegisteredFunction] = {}
        self._available_backends = available_backends or frozenset({"in_process"})

    def register(self, tool: RegisteredFunction) -> "ToolRegistry":
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._validate_execution_boundary(tool)
        self._tools[tool.name] = tool
        return self

    def get(self, name: str) -> RegisteredFunction | None:
        return self._tools.get(name)

    def require(self, name: str) -> RegisteredFunction:
        tool = self.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools)) or "<none>"
            raise KeyError(f"Unknown Agent tool `{name}`. Available tools: {available}")
        return tool

    def list_tools(self) -> list[RegisteredFunction]:
        return [self._tools[name] for name in sorted(self._tools)]

    def list_specs(self):
        return [tool.spec for tool in self.list_tools()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

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
