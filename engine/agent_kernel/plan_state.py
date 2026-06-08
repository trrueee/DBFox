from __future__ import annotations

from typing import Any

from engine.agent_kernel.schemas import PlanPatch, PlanState, PlanStep


TOOL_FINAL_STATUS_OPERATION = {
    "success": ("mark_completed", "Tool execution completed."),
    "failed": ("mark_failed", "Tool execution failed."),
    "skipped": ("skip_step", "Tool execution skipped."),
}


def apply_plan_patches(
    plan: dict[str, Any] | PlanState | None,
    patches: list[PlanPatch],
) -> dict[str, Any]:
    state = _plan_state(plan)
    steps_by_id = {step.id: step for step in state.steps}
    ordered_ids = [step.id for step in state.steps]

    for patch in patches:
        if patch.operation == "clear_plan":
            steps_by_id.clear()
            ordered_ids.clear()
            continue

        if patch.operation == "create_plan":
            steps_by_id.clear()
            ordered_ids.clear()
            if patch.step is not None:
                _upsert_step(steps_by_id, ordered_ids, patch.step)
            continue

        if patch.operation == "add_step" and patch.step is not None:
            _upsert_step(steps_by_id, ordered_ids, patch.step)
            continue

        if patch.operation == "update_step" and patch.step is not None:
            current = steps_by_id.get(patch.step.id)
            merged = _merge_step(current, patch.step)
            _upsert_step(steps_by_id, ordered_ids, merged)
            continue

        step_id = patch.step_id or (patch.step.id if patch.step is not None else None)
        if not step_id or step_id not in steps_by_id:
            continue

        if patch.operation == "mark_running":
            steps_by_id[step_id] = steps_by_id[step_id].model_copy(update={"status": "running"})
        elif patch.operation in {"mark_completed", "complete_step"}:
            steps_by_id[step_id] = steps_by_id[step_id].model_copy(update={"status": "completed"})
        elif patch.operation in {"mark_failed", "fail_step"}:
            steps_by_id[step_id] = steps_by_id[step_id].model_copy(update={"status": "failed"})
        elif patch.operation == "skip_step":
            steps_by_id[step_id] = steps_by_id[step_id].model_copy(update={"status": "skipped"})

    return PlanState(steps=[steps_by_id[step_id] for step_id in ordered_ids]).model_dump(mode="json")


def plan_patches_for_tool_execution(
    plan: dict[str, Any] | PlanState | None,
    *,
    tool_name: str,
    status: str,
) -> list[PlanPatch]:
    step = _matching_tool_step(plan, tool_name)
    if step is None:
        return []

    patches: list[PlanPatch] = []
    if step.status != "running":
        patches.append(
            PlanPatch(
                operation="mark_running",
                step_id=step.id,
                reason="Tool execution started.",
            )
        )

    final_operation = TOOL_FINAL_STATUS_OPERATION.get(status)
    if final_operation is None:
        return patches
    operation, reason = final_operation
    patches.append(
        PlanPatch(
            operation=operation,  # type: ignore[arg-type]
            step_id=step.id,
            reason=reason,
        )
    )
    return patches


def _plan_state(plan: dict[str, Any] | PlanState | None) -> PlanState:
    if isinstance(plan, PlanState):
        return plan
    if isinstance(plan, dict):
        return PlanState.model_validate(plan)
    return PlanState()


def _upsert_step(steps_by_id: dict[str, PlanStep], ordered_ids: list[str], step: PlanStep) -> None:
    if step.id not in steps_by_id:
        ordered_ids.append(step.id)
    steps_by_id[step.id] = step


def _merge_step(current: PlanStep | None, patch: PlanStep) -> PlanStep:
    if current is None:
        return patch
    update = patch.model_dump(exclude_unset=True)
    return current.model_copy(update=update)


def _matching_tool_step(plan: dict[str, Any] | PlanState | None, tool_name: str) -> PlanStep | None:
    if not tool_name:
        return None
    state = _plan_state(plan)
    candidates = _candidate_tool_names(tool_name)
    for candidate in candidates:
        for status in ("pending", "running"):
            for step in state.steps:
                if step.tool_name == candidate and step.status == status:
                    return step
    return None


def _candidate_tool_names(tool_name: str) -> list[str]:
    if tool_name == "sql.skip_execution":
        return ["sql.skip_execution", "sql.execute_readonly"]
    return [tool_name]
