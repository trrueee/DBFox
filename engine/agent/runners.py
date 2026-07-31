"""Focused model-turn and tool-invocation execution boundaries."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from engine.agent.control import LeaseAwareRunControl
from engine.agent.turn import ModelTurnResult, TurnStreamAssembler, TurnStreamItem
from engine.tools.runtime import ToolExecutor
from engine.tools.runtime.base import BaseTool
from engine.tools.runtime.executor import ToolOperation
from engine.tools.runtime.result import ToolResult


class ModelTurnRunner:
    def run(
        self,
        *,
        stream: Iterable[TurnStreamItem],
        publish: Callable[[Iterable[TurnStreamItem]], Iterable[TurnStreamItem]],
        control: LeaseAwareRunControl,
    ) -> ModelTurnResult:
        control.checkpoint()
        return TurnStreamAssembler().consume(publish(stream))


class ToolInvocationRunner:
    def __init__(self, executor: ToolExecutor) -> None:
        self.executor = executor

    def run(
        self,
        *,
        tool: BaseTool,
        scope_key: str,
        operation: ToolOperation,
        control: LeaseAwareRunControl,
        cancel_action: Callable[[], None] | None,
        on_attempt: Callable[[int], None] | None,
    ) -> ToolResult:
        result = self.executor.execute(
            tool=tool,
            scope_key=scope_key,
            operation=operation,
            should_cancel=control.is_cancel_requested,
            cancel_action=cancel_action,
            on_attempt=on_attempt,
            deadline=control.deadline,
        )
        # The durable ToolInvocation must be settled before cancellation or lease
        # loss is propagated.  The caller performs that settlement and checkpoints
        # immediately afterwards.
        return result
