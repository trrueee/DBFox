from __future__ import annotations

from engine.tools.runtime.base import BaseTool


IN_PROCESS_CAPABILITIES = frozenset({"metadata_read", "metadata_write", "database_read"})

TOOL_GROUP_MAP: dict[str, str] = {
    "environment.": "environment",
    "schema.": "schema",
    "db.": "db",
    "result.": "result",
    "chart.": "chart",
    "answer.": "answer",
    "question.": "control",
    "escalate.": "control",
    "plan.": "control",
    "sql.": "sql",
}


def tool_to_group(tool_name: str) -> str | None:
    for prefix, group in TOOL_GROUP_MAP.items():
        if tool_name.startswith(prefix):
            return group
    return None


class ToolRegistry:
    def __init__(self, *, available_backends: frozenset[str] | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._available_backends = available_backends or frozenset({"in_process"})

    def register(self, tool: BaseTool) -> "ToolRegistry":
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._validate_execution_boundary(tool)
        self._tools[tool.name] = tool
        return self

    def force_register(self, tool: BaseTool) -> "ToolRegistry":
        self._validate_execution_boundary(tool)
        self._tools[tool.name] = tool
        return self

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def require(self, name: str) -> BaseTool:
        tool = self.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools)) or "<none>"
            raise KeyError(f"Unknown Agent tool `{name}`. Available tools: {available}")
        return tool

    def list_tools(self) -> list[BaseTool]:
        return [self._tools[name] for name in sorted(self._tools)]

    def list_specs(self):
        return [tool.spec for tool in self.list_tools()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def _validate_execution_boundary(self, tool: BaseTool) -> None:
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
        if tool.policy.side_effect == "read" and not capabilities.intersection(
            {"metadata_read", "database_read", "filesystem_read"}
        ):
            raise ValueError(f"Read tool '{tool.name}' must declare its read capability.")
        if tool.policy.side_effect in {"write", "destructive"} and not capabilities.intersection(
            {"metadata_write", "database_write", "filesystem_write"}
        ):
            raise ValueError(f"Write tool '{tool.name}' must declare its write capability.")
