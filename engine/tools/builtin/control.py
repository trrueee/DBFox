from __future__ import annotations

from engine.agent.repositories.plan import PlanRepository
from engine.agent.repositories.question import QuestionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.tools.builtin.contracts import (
    AcknowledgementOutput,
    RequestClarificationInput,
    UpdatePlanInput,
    UpdatePlanOutput,
)
from engine.tools.runtime import (
    ControlCommand,
    ControlCommandContext,
    ControlCommandResult,
    ControlDisposition,
    ToolPolicy,
    ToolPresentation,
)


class RequestClarificationCommand(
    ControlCommand[RequestClarificationInput, AcknowledgementOutput]
):
    name = "request_clarification"
    description = (
        "Pause the same Run and ask one necessary business clarification. Use only "
        "when catalog exploration and prior context cannot resolve the ambiguity. "
        "Never use this for authorization, approval, progress reporting, or errors."
    )
    input_model = RequestClarificationInput
    output_model = AcknowledgementOutput
    presentation = ToolPresentation(
        title="请求补充信息",
        category="manage",
        visibility="details",
        progress="none",
    )
    policy = ToolPolicy(risk_level="safe")

    def handle(
        self,
        command_input: RequestClarificationInput,
        context: ControlCommandContext,
    ) -> ControlCommandResult[AcknowledgementOutput]:
        ToolInvocationRepository(context.db).mark_waiting_input(
            lease=context.lease,
            invocation_id=context.invocation_id,
        )
        QuestionRepository(context.db).request(
            lease=context.lease,
            run_id=context.run_id,
            turn_id=context.turn_id,
            tool_invocation_id=context.invocation_id,
            question=command_input.question,
            reason=command_input.reason,
            options=[
                option.model_dump(mode="json")
                for option in command_input.options
            ],
            allow_free_text=command_input.allow_free_text,
        )
        return ControlCommandResult(
            disposition=ControlDisposition.WAITING_INPUT
        )


class UpdatePlanCommand(ControlCommand[UpdatePlanInput, UpdatePlanOutput]):
    name = "update_plan"
    description = (
        "Create or materially update the visible plan for a genuinely multi-part "
        "analysis. Keep step IDs stable, allow at most one in-progress step, and "
        "attach exact Artifact IDs to completed evidence-required steps."
    )
    input_model = UpdatePlanInput
    output_model = UpdatePlanOutput
    presentation = ToolPresentation(
        title="更新分析计划",
        category="manage",
        visibility="summary",
    )
    policy = ToolPolicy(risk_level="safe")

    def handle(
        self,
        command_input: UpdatePlanInput,
        context: ControlCommandContext,
    ) -> ControlCommandResult[UpdatePlanOutput]:
        plan = PlanRepository(context.db).update(
            lease=context.lease,
            run_id=context.run_id,
            turn_id=context.turn_id,
            objective=command_input.objective,
            steps=command_input.steps,
            summary=command_input.summary,
        )
        output = UpdatePlanOutput(
            plan_id=plan.id,
            version=plan.version,
            objective=plan.objective,
            steps=plan.steps,
            status=plan.status.value,
            summary=plan.summary,
        )
        completed = sum(
            step.status.value == "completed"
            for step in plan.steps
        )
        return ControlCommandResult(
            disposition=ControlDisposition.SETTLED,
            output=output,
            summary=(
                f"分析计划已更新，{completed}/{len(plan.steps)} 个步骤完成。"
            ),
            facts={
                "plan_id": plan.id,
                "version": plan.version,
                "objective": plan.objective,
                "status": plan.status.value,
                "steps": [
                    step.model_dump(mode="json")
                    for step in plan.steps
                ],
                "summary": plan.summary,
            },
        )
