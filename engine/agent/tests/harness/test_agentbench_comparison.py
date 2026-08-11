from __future__ import annotations

from scripts.agentbench.comparison import compare_summaries


def _summary(
    *,
    success: float,
    tokens: float,
    latency: float,
    safety: int = 0,
    duplicate_ratio: float = 0,
    failed_ratio: float = 0,
    unscored: int = 0,
    case_passed: bool = True,
):
    return {
        "dataset": {
            "dataset_id": "dbfox-agent-regression",
            "dataset_version": "1.0.0",
        },
        "scored_trials": 10,
        "success_rate": success,
        "safety_veto_count": safety,
        "unscored_trials": unscored,
        "tokens": {"median": tokens},
        "latency_ms": {"p90": latency},
        "duplicate_tool_call_ratio": {"median": duplicate_ratio},
        "failed_tool_call_ratio": {"median": failed_ratio},
        "by_case": {
            "case": {"all_repetitions_passed": case_passed},
        },
    }


def test_paired_gate_accepts_changes_inside_declared_thresholds() -> None:
    result = compare_summaries(
        _summary(success=0.90, tokens=100, latency=1000),
        _summary(success=0.89, tokens=110, latency=1150),
    )
    assert result.passed


def test_paired_gate_rejects_safety_or_material_quality_regression() -> None:
    result = compare_summaries(
        _summary(success=0.95, tokens=100, latency=1000),
        _summary(
            success=0.85,
            tokens=130,
            latency=1400,
            safety=1,
            duplicate_ratio=0.2,
            failed_ratio=0.2,
            unscored=1,
            case_passed=False,
        ),
    )
    assert not result.passed
    assert {
        "no_safety_veto",
        "success_rate",
        "median_tokens",
        "p90_latency",
        "no_new_infrastructure_failures",
        "no_case_regression",
        "duplicate_tool_ratio",
        "failed_tool_ratio",
    } <= set(result.failed_checks)
