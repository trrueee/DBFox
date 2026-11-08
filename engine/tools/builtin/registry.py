from __future__ import annotations

from engine.tools.runtime import ToolRegistry

CORE_OWNER = "dbfox.core"
CONVERSATION_OWNER = "dbfox.conversation"


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
