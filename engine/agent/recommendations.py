from __future__ import annotations

from typing import Any

from engine.agent.types import FollowUpSuggestion, ResultProfile


def suggest_followups(
    question: str,
    result_profile: ResultProfile | None,
    chart_suggestion: dict[str, Any] | None,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
) -> list[FollowUpSuggestion]:
    suggestions: list[FollowUpSuggestion] = []
    patterns = set(result_profile.detected_patterns if result_profile else [])

    if "empty_result" in patterns:
        suggestions.extend(
            [
                FollowUpSuggestion(
                    label="Widen filters",
                    question=f"{question} with a wider time range or looser filters",
                    reason="The current query returned no rows.",
                    action_type="ask",
                ),
                FollowUpSuggestion(
                    label="Preview raw data",
                    question="Show a small sample of the source table before filters",
                    reason="A raw preview helps verify whether filters or data availability caused the empty result.",
                    action_type="ask",
                ),
            ]
        )
    elif "time_series" in patterns:
        suggestions.extend(
            [
                FollowUpSuggestion(
                    label="Compare period",
                    question=f"Compare this result with the previous comparable period: {question}",
                    reason="Trend results are easier to judge against a baseline.",
                    action_type="ask",
                ),
                FollowUpSuggestion(
                    label="Find anomaly dates",
                    question=f"Find the dates or intervals with the largest change for: {question}",
                    reason="The result appears time-based, so anomaly dates are useful next evidence.",
                    action_type="ask",
                ),
            ]
        )
    elif "category_breakdown" in patterns or "top_k" in patterns:
        suggestions.extend(
            [
                FollowUpSuggestion(
                    label="Drill into top value",
                    question=f"Drill into the top category from this result: {question}",
                    reason="Category breakdowns usually need a second pass on the largest contributor.",
                    action_type="ask",
                ),
                FollowUpSuggestion(
                    label="Show share",
                    question=f"Calculate each category's share for: {question}",
                    reason="Absolute values are clearer when paired with contribution share.",
                    action_type="ask",
                ),
            ]
        )
    else:
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
