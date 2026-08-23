"""Capability-neutral executable tools for Agent Core verification."""

from __future__ import annotations

from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
    ToolRecoveryPolicy,
    ToolRegistry,
)


class VerificationInput(ToolInputModel):
    value: str | None = None
    limit: int = 20


class VerificationOutput(ToolOutputModel):
    ok: bool


class VerificationTool(BaseTool[VerificationInput, VerificationOutput]):
    name = "verification_read"
    group = "verification"
    description = "Execute a bounded capability-neutral verification operation."
    input_model = VerificationInput
    output_model = VerificationOutput
    presentation = ToolPresentation(title="Verification", category="explore")

    def __init__(
        self,
        *,
        name: str = "verification_read",
        recovery: ToolRecoveryPolicy = ToolRecoveryPolicy.NEVER_RETRY,
        requires_approval: bool = False,
    ) -> None:
        self.name = name
        self.policy = ToolPolicy(requires_approval=requires_approval)
        self.execution = ToolExecutionSpec(
            recovery=recovery,
            retryable=recovery is ToolRecoveryPolicy.RETRY_SAFE,
        )

    def run(self, tool_input, context):
        del tool_input, context
        return VerificationOutput(ok=True)

    def reconcile(self, tool_input, context):
        from engine.tools.runtime import ToolReconciliation

        del tool_input, context
        return ToolReconciliation(status="not_applied")


def verification_registry(
    *,
    recovery: ToolRecoveryPolicy = ToolRecoveryPolicy.NEVER_RETRY,
    requires_approval: bool = False,
) -> ToolRegistry:
    return ToolRegistry().register(
        VerificationTool(
            recovery=recovery,
            requires_approval=requires_approval,
        )
    )
