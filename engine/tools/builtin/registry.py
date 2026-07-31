from __future__ import annotations

from engine.tools.builtin.catalog import (
    CatalogOverviewTool,
    CatalogRefreshTool,
    SchemaInspectTool,
    SchemaListTool,
    SchemaSearchTool,
)
from engine.tools.builtin.control import (
    RequestClarificationCommand,
    UpdatePlanCommand,
)
from engine.tools.builtin.query import (
    DataPreviewTool,
    SqlExecuteReadonlyTool,
    SqlValidateTool,
)
from engine.tools.builtin.results import (
    ChartCreateTool,
    ResultInspectTool,
    ResultProfileTool,
)
from engine.tools.runtime import ToolRegistry


def register_dbfox_tools() -> ToolRegistry:
    """Build the complete model-function registry for one DBFox Agent process."""

    registry = ToolRegistry()
    registry.register(RequestClarificationCommand())
    registry.register(UpdatePlanCommand())
    registry.register(CatalogOverviewTool())
    registry.register(CatalogRefreshTool())
    registry.register(SchemaListTool())
    registry.register(SchemaSearchTool())
    registry.register(SchemaInspectTool())
    registry.register(DataPreviewTool())
    registry.register(SqlValidateTool())
    registry.register(SqlExecuteReadonlyTool())
    registry.register(ResultInspectTool())
    registry.register(ResultProfileTool())
    registry.register(ChartCreateTool())
    return registry
