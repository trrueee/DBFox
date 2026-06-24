from __future__ import annotations

from engine.tools.runtime.base import BaseTool

TOOL_GROUP_MAP: dict[str, str] = {
    "environment.": "environment",
    "schema.": "schema",
    "db.": "db",
    "result.": "result",
    "chart.": "chart",
    "answer.": "answer",
    "escalate.": "control",
    "sql.": "sql",
}


def tool_to_group(tool_name: str) -> str | None:
    for prefix, group in TOOL_GROUP_MAP.items():
        if tool_name.startswith(prefix):
            return group
    return None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> "ToolRegistry":
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool
        return self

    def force_register(self, tool: BaseTool) -> "ToolRegistry":
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
