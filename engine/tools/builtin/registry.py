from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from engine.agent.artifact import Artifact
from engine.representation import ArtifactRepresentationDescriptor
from engine.tools.runtime import ToolRegistry

if TYPE_CHECKING:
    from engine.dlc.snapshot import ToolContribution
    from engine.local_execution.broker import LocalExecutionBroker
    from engine.workbench_presentations import WorkbenchPresentationBroker

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


def register_artifact_read(
    registry: ToolRegistry,
    describe: Callable[[Artifact], tuple[ArtifactRepresentationDescriptor, ...]],
) -> None:
    from engine.tools.builtin.artifact import ArtifactReadTool

    tool = ArtifactReadTool(describe)
    registry.register(tool, owner=CONVERSATION_OWNER, provider_name=tool.name)


def register_workbench_open(registry: ToolRegistry, broker: WorkbenchPresentationBroker) -> None:
    from engine.tools.builtin.workbench import OpenArtifactTool

    tool = OpenArtifactTool(broker)
    registry.register(tool, owner="dbfox.workbench", provider_name=tool.name)


def local_execution_contributions(
    broker: LocalExecutionBroker, legacy: ToolContribution,
) -> tuple[ToolContribution, ...]:
    from engine.dlc.snapshot import ToolContribution
    from engine.local_execution.tools import (
        CommandEnvironment, CommandInspect, CommandResult, CommandStart, CommandStdin, CommandStop, bind_command_run,
    )

    return (
        ToolContribution(
            bind_command_run(broker, legacy.tool), legacy.owner_id, legacy.package_digest, legacy.provider_name,
            host_supervised_process=True,
        ),
        *(ToolContribution(
            tool, legacy.owner_id, legacy.package_digest,
            host_supervised_process="subprocess" in tool.execution.capabilities,
        ) for tool in (
            CommandEnvironment(broker), CommandStart(broker), CommandInspect(broker),
            CommandStdin(broker), CommandStop(broker), CommandResult(broker),
        )),
    )
