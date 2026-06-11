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

FailureLayer = Literal[
    "planner",
    "schema",
    "semantic",
    "query_plan",
    "sql_generation",
    "sql_validation",
    "execution",
    "result_analysis",
    "policy",
    "unknown",
]


class ProgressDecision(BaseModel):
    """Structured progress assessment — Agent v2 with failure diagnosis.

    Called after every observe cycle.  Judges whether the task is complete,
    needs more work, requires a revised plan, or should be clarified.

    When failing, it diagnoses the failure layer and proposes a recovery
    strategy so the Planner and model can self-correct instead of giving up.
    """

    # ---- Primary status -------------------------------------------------------
    status: ProgressStatus = Field(
        description=(
            "complete  — user goal satisfied, finalize.\n"
            "continue  — more tool work under same plan.\n"
            "replan    — plan insufficient; go back to Planner with recovery hints.\n"
            "clarify   — user intent ambiguous; ask user.\n"
            "blocked   — policy blocked action but safe alternative possible.\n"
            "failed    — task cannot be completed."
        )
    )

    reason_summary: str = Field(
        default="",
        description="Concise explanation for debugging and planner context.",
    )

    # ---- Completion detail -----------------------------------------------------
    completion_reason: str | None = Field(
        default=None,
        description="When complete, why (e.g. 'answer synthesized', 'max steps reached').",
    )

    # ---- Failure diagnosis (Agent v2) -----------------------------------------
    failure_layer: FailureLayer | None = Field(
        default=None,
        description=(
            "Which layer caused the failure.  Drives recovery strategy.\n"
            "planner        — wrong task type or tool scope.\n"
            "schema         — unknown table, unknown column, stale catalog.\n"
            "semantic       — business term not resolved, metric ambiguous.\n"
            "query_plan     — bad metrics/dimensions/filters, missing join path.\n"
            "sql_generation — LLM produced invalid or unsafe SQL.\n"
            "sql_validation — guardrail / trust gate / schema hallucination.\n"
            "execution      — DB error, timeout, connection.\n"
            "result_analysis — empty result, unexpected profile.\n"
            "policy         — blocked by PolicyGate.\n"
            "unknown        — cannot diagnose."
        ),
    )

    root_cause: str | None = Field(
        default=None,
        description="Specific root cause, e.g. 'column account_id not found in orders'.",
    )

    recovery_strategy: str | None = Field(
        default=None,
        description=(
            "What to do next.  E.g. 'describe candidates table and rebuild join path', "
            "'loosen time filter', 'ask user to clarify metric definition'."
        ),
    )

    # ---- Retry control ---------------------------------------------------------
    should_retry: bool = Field(
        default=False,
        description="True when the model should retry with the same plan (transient error).",
    )

    retry_budget: int = Field(
        default=0,
        description="How many more retries are allowed before escalating to user or finalizing.",
    )

    # ---- Replan / recovery routing ---------------------------------------------
    should_replan: bool = Field(
        default=False,
        description="True when the Planner should create a revised plan.",
    )

    should_finalize: bool = Field(
        default=False,
        description="True when the run should finalize immediately.",
    )

    revised_plan_hint: dict | None = Field(
        default=None,
        description=(
            "When replanning: suggested task_type, tool_groups, execution_mode. "
            "The Planner uses this to scope the new plan."
        ),
    )

    # ---- User interaction -----------------------------------------------------
    should_ask_user: bool = Field(
        default=False,
        description="True when the agent should ask the user a clarification question.",
    )

    clarification_question: str | None = Field(
        default=None,
        description="When clarify, the question to present to the user.",
    )

    # ---- Next-step guidance (coding-agent supervisor output) -------------------
    next_action_hint: str | None = Field(
        default=None,
        description=(
            "Concrete next action for the ReAct model, e.g. "
            "'check refund rate trend for last 30 days'."
        ),
    )

    missing_evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Evidence still needed before the goal is satisfied, "
            "e.g. ['refund trend', 'new customer orders']."
        ),
    )

    user_visible_update: str | None = Field(
        default=None,
        description=(
            "Short user-readable status for the timeline UI. "
            "No chain-of-thought — action summary only."
        ),
    )

    next_instruction: str | None = Field(
        default=None,
        description="When continue, a brief hint for the model about what to do next.",
    )

    next_tool_groups: list[str] = Field(
        default_factory=list,
        description="When replanning: suggested tool groups for the new plan.",
    )

    should_consult_memory: bool = Field(
        default=False,
        description="True when the agent should search memory before the next attempt.",
    )
