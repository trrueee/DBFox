from __future__ import annotations

from typing import Any

from engine.agent_core.types import FollowUpSuggestion


def suggest_followups(
    question: str,
    chart_suggestion: dict[str, Any] | None,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
) -> list[FollowUpSuggestion]:
    suggestions: list[FollowUpSuggestion] = []

    # Without result_profile, fall back to the generic suggestion
    suggestions.append(
        FollowUpSuggestion(
            label="Break down",
            question=f"Break this result down by a useful business dimension: {question}",
            reason="A dimension breakdown is often the next step after a direct query.",
            action_type="ask",
        )
    )

    if chart_suggestion and chart_suggestion.get("type") not in (None, "table"):
        suggestions.append(
            FollowUpSuggestion(
                label="Open chart",
                question="Render this result as the suggested chart",
                reason=str(chart_suggestion.get("reason") or "The result has a chartable shape."),
                action_type="chart",
            )
        )

    if sql and safety and safety.get("can_execute") and (execution or {}).get("success"):
        suggestions.append(
            FollowUpSuggestion(
                label="Save Golden SQL",
                question="Save this SQL as a Golden SQL case",
                reason="The query passed safety checks and produced data, making it a useful regression case.",
                action_type="save_golden_sql",
            )
        )

    return suggestions[:4]


def recommendation_texts(suggestions: list[FollowUpSuggestion]) -> list[str]:
    return [suggestion.question for suggestion in suggestions[:3]]
