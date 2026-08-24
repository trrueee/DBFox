from __future__ import annotations

from verification.bench.framework.comparison import compare_summaries


def _summary(*, turns: float, success: float = 1.0, duplicates: float = 0.0):
    return {
        "suite": {
            "suite_id": "core.loop.scripted",
            "suite_version": "1.0.0",
            "metrics": [
                {"name": "task.success_rate", "direction": "higher_is_better"},
                {"name": "runtime.turns", "direction": "lower_is_better"},
                {"name": "runtime.duplicate_tool_calls", "direction": "zero_is_best"},
            ],
        },
        "scored_trials": 3,
        "unscored_trials": 0,
        "success_rate": success,
        "metrics": {
            "task.success_rate": {"median": success},
            "runtime.turns": {"median": turns},
            "runtime.duplicate_tool_calls": {"median": duplicates},
        },
    }


def test_generic_comparison_uses_manifest_metric_directions() -> None:
    result = compare_summaries(
        _summary(turns=3),
        _summary(turns=2),
    )
    assert result.passed


def test_generic_comparison_rejects_regression_without_domain_knowledge() -> None:
    result = compare_summaries(
        _summary(turns=2),
        _summary(turns=3, success=0.7, duplicates=1),
    )
    assert not result.passed
    assert {
        "success_rate",
        "metric:task.success_rate",
        "metric:runtime.turns",
        "metric:runtime.duplicate_tool_calls",
    } <= set(result.failed_checks)
