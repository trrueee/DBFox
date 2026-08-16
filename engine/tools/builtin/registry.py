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
from engine.tools.builtin.conversation import ConversationReadTool, ConversationSearchTool
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
from engine.tools.builtin.workspace import WorkspaceFileReadTool, WorkspaceFileSearchTool
from engine.tools.runtime import ToolRegistry

CORE_OWNER = "dbfox.core"
CONVERSATION_OWNER = "dbfox.conversation"
DATA_OWNER = "dbfox.data"
WORKSPACE_OWNER = "dbfox.workspace"


def register_core_functions(registry: ToolRegistry) -> None:
    """Register Runtime-owned control functions.

    These functions are the stable Kernel surface and must never be attributed
    to a domain extension such as ``dbfox.data``.
    """

    registry.register(RequestClarificationCommand(), owner=CORE_OWNER)
    registry.register(UpdatePlanCommand(), owner=CORE_OWNER)


def register_conversation_functions(registry: ToolRegistry) -> None:
    """Register Conversation-owned recall functions."""

    registry.register(ConversationSearchTool(), owner=CONVERSATION_OWNER)
    registry.register(ConversationReadTool(), owner=CONVERSATION_OWNER)


def register_data_extension(registry: ToolRegistry) -> None:
    """Register the built-in Data capability family."""

    registry.register(CatalogOverviewTool(), owner=DATA_OWNER)
    registry.register(CatalogRefreshTool(), owner=DATA_OWNER)
    registry.register(SchemaListTool(), owner=DATA_OWNER)
    registry.register(SchemaSearchTool(), owner=DATA_OWNER)
    registry.register(SchemaInspectTool(), owner=DATA_OWNER)
    registry.register(DataPreviewTool(), owner=DATA_OWNER)
    registry.register(SqlValidateTool(), owner=DATA_OWNER)
    registry.register(SqlExecuteReadonlyTool(), owner=DATA_OWNER)
    registry.register(ResultInspectTool(), owner=DATA_OWNER)
    registry.register(ResultProfileTool(), owner=DATA_OWNER)
    registry.register(ChartCreateTool(), owner=DATA_OWNER)


def register_workspace_extension(registry: ToolRegistry) -> None:
    """Register the Workspace read-only capability family."""

    registry.register(WorkspaceFileReadTool(), owner=WORKSPACE_OWNER)
    registry.register(WorkspaceFileSearchTool(), owner=WORKSPACE_OWNER)


def register_dbfox_tools() -> ToolRegistry:
    """Build the complete model-function registry for one DBFox Agent process.

    Short-term facade: new call sites should use the owner-scoped registration
    functions above, then freeze the Registry before serving Runs. This function
    is removed once every production composition call site has migrated.
    """

    registry = ToolRegistry()
    register_core_functions(registry)
    register_conversation_functions(registry)
    register_data_extension(registry)
    register_workspace_extension(registry)
    return registry.freeze()
