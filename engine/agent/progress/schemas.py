from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProgressStatus = Literal[
    "complete",
    "continue",
    "replan",
    "clarify",
    "blocked",
    "failed",
]


class ProgressDecision(BaseModel):
    """Structured progress assessment produced by the LLM Progress Judge.

    Called after every observe cycle (and when the model produces no tool_calls)
    to decide whether the user's task is truly complete, needs more work,
    requires a revised plan, or should be clarified with the user.

    This is NOT a rule-based checker. It judges semantically from the full
    execution trace: user question, plan directive, tool observations,
    artifacts, errors, and the model's latest response.
    """

    status: ProgressStatus = Field(
        description=(
            "complete: user goal satisfied, finalize.\n"
            "continue: more tool use / reasoning needed under same plan.\n"
            "replan: current plan or tool scope is insufficient; go back to Planner.\n"
            "clarify: user goal cannot be safely inferred; ask user.\n"
            "blocked: policy blocked the requested action but safe alternative possible.\n"
            "failed: task cannot be completed."
        )
    )
    reason_summary: str = Field(
        description="Concise explanation of the decision for debugging."
    )
    next_instruction: str | None = Field(
        default=None,
        description="When status=continue, a brief hint for the model about what to do next.",
    )
    revised_plan_hint: dict | None = Field(
        default=None,
        description="When status=replan, hints for the Planner: suggested task_type, tool_groups, execution_mode.",
    )
    clarification_question: str | None = Field(
        default=None,
        description="When status=clarify, the question to present to the user.",
    )
    should_retry: bool = Field(
        default=False,
        description="True when the model should retry with the same plan (e.g., transient error).",
    )
    should_replan: bool = Field(
        default=False,
        description="True when the Planner should create a revised plan.",
    )
    should_finalize: bool = Field(
        default=False,
        description="True when the run should finalize immediately.",
    )
