from __future__ import annotations

from engine.tools.runtime import ToolRegistry

CORE_OWNER = "dbfox.core"
CONVERSATION_OWNER = "dbfox.conversation"
REMOTE_JOB_OWNER = "dbfox.remote_job"


def register_core_functions(registry: ToolRegistry) -> None:
    """Register Runtime-owned control functions.

    These functions are the stable Kernel surface and must never be attributed
    to a domain extension such as ``dbfox.data``.
    """

    from engine.tools.builtin.control import (
        RequestClarificationCommand,
        UpdatePlanCommand,
    )

    registry.register(RequestClarificationCommand(), owner=CORE_OWNER)
    registry.register(UpdatePlanCommand(), owner=CORE_OWNER)


def register_conversation_functions(registry: ToolRegistry) -> None:
    """Register Conversation-owned recall functions."""

    from engine.tools.builtin.conversation import (
        ConversationReadTool,
        ConversationSearchTool,
    )

    registry.register(ConversationSearchTool(), owner=CONVERSATION_OWNER)
    registry.register(ConversationReadTool(), owner=CONVERSATION_OWNER)


def register_remote_job_extension(registry: ToolRegistry) -> None:
    """Register the built-in Remote Job capability family."""

    from engine.tools.builtin.remote_job import (
        RemoteJobCancelTool,
        RemoteJobStatusTool,
        RemoteJobSubmitTool,
    )

    registry.register(RemoteJobSubmitTool(), owner=REMOTE_JOB_OWNER)
    registry.register(RemoteJobStatusTool(), owner=REMOTE_JOB_OWNER)
    registry.register(RemoteJobCancelTool(), owner=REMOTE_JOB_OWNER)
