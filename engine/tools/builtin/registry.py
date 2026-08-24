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

    clarification = RequestClarificationCommand()
    update_plan = UpdatePlanCommand()
    registry.register(clarification, owner=CORE_OWNER, provider_name=clarification.name)
    registry.register(update_plan, owner=CORE_OWNER, provider_name=update_plan.name)


def register_conversation_functions(registry: ToolRegistry) -> None:
    """Register Conversation-owned recall functions."""

    from engine.tools.builtin.conversation import (
        ConversationReadTool,
        ConversationSearchTool,
    )

    search = ConversationSearchTool()
    read = ConversationReadTool()
    registry.register(search, owner=CONVERSATION_OWNER, provider_name=search.name)
    registry.register(read, owner=CONVERSATION_OWNER, provider_name=read.name)


def register_remote_job_extension(registry: ToolRegistry) -> None:
    """Register the built-in Remote Job capability family."""

    from engine.tools.builtin.remote_job import (
        RemoteJobCancelTool,
        RemoteJobStatusTool,
        RemoteJobSubmitTool,
    )

    submit = RemoteJobSubmitTool()
    status = RemoteJobStatusTool()
    cancel = RemoteJobCancelTool()
    registry.register(submit, owner=REMOTE_JOB_OWNER, provider_name=submit.name)
    registry.register(status, owner=REMOTE_JOB_OWNER, provider_name=status.name)
    registry.register(cancel, owner=REMOTE_JOB_OWNER, provider_name=cancel.name)
