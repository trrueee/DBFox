from __future__ import annotations

from engine.agent_core.recommendations import suggest_followups


def test_followups_do_not_offer_chart_for_non_chartable_suggestion():
    suggestions = suggest_followups(
        question="show users",
        chart_suggestion={"type": "none", "chartable": False, "series": []},
        sql=None,
        safety=None,
        execution=None,
    )

    assert all(suggestion.action_type != "chart" for suggestion in suggestions)
