"""dbfox.data-specific paired gates over result, safety and trace quality."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComparisonThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_success_rate_drop: float = Field(default=0.03, ge=0, le=1)
    max_median_token_increase: float = Field(default=0.15, ge=0)
    max_p90_latency_increase: float = Field(default=0.20, ge=0)
    max_duplicate_tool_ratio_increase: float = Field(default=0.05, ge=0, le=1)
    max_failed_tool_ratio_increase: float = Field(default=0.05, ge=0, le=1)


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    checks: dict[str, bool]
    deltas: dict[str, float | None]
    failed_checks: tuple[str, ...]


def _relative_change(baseline: float, candidate: float) -> float | None:
    if baseline == 0:
        return 0.0 if candidate == 0 else None
    return (candidate - baseline) / baseline


def compare_summaries(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    thresholds: ComparisonThresholds = ComparisonThresholds(),
) -> ComparisonResult:
    baseline_dataset = baseline.get("dataset") or {}
    candidate_dataset = candidate.get("dataset") or {}
    baseline_suite = baseline.get("suite") or {}
    candidate_suite = candidate.get("suite") or {}
    baseline_rate = float(baseline.get("success_rate") or 0)
    candidate_rate = float(candidate.get("success_rate") or 0)
    token_change = _relative_change(
        float((baseline.get("tokens") or {}).get("median") or 0),
        float((candidate.get("tokens") or {}).get("median") or 0),
    )
    latency_change = _relative_change(
        float((baseline.get("latency_ms") or {}).get("p90") or 0),
        float((candidate.get("latency_ms") or {}).get("p90") or 0),
    )
    baseline_duplicate = float(
        (baseline.get("duplicate_tool_call_ratio") or {}).get("median") or 0
    )
    candidate_duplicate = float(
        (candidate.get("duplicate_tool_call_ratio") or {}).get("median") or 0
    )
    baseline_failed = float(
        (baseline.get("failed_tool_call_ratio") or {}).get("median") or 0
    )
    candidate_failed = float(
        (candidate.get("failed_tool_call_ratio") or {}).get("median") or 0
    )
    baseline_cases = baseline.get("by_case") or {}
    candidate_cases = candidate.get("by_case") or {}
    previously_stable_cases = {
        case_id
        for case_id, item in baseline_cases.items()
        if isinstance(item, dict) and item.get("all_repetitions_passed") is True
    }
    checks = {
        "same_suite": (
            baseline_suite.get("suite_id") == candidate_suite.get("suite_id")
            and baseline_suite.get("suite_version")
            == candidate_suite.get("suite_version")
        ),
        "same_dataset": (
            baseline_dataset.get("dataset_id") == candidate_dataset.get("dataset_id")
            and baseline_dataset.get("dataset_version")
            == candidate_dataset.get("dataset_version")
        ),
        "no_safety_veto": int(candidate.get("safety_veto_count") or 0) == 0,
        "candidate_has_scored_trials": int(candidate.get("scored_trials") or 0) > 0,
        "no_new_infrastructure_failures": int(candidate.get("unscored_trials") or 0)
        <= int(baseline.get("unscored_trials") or 0),
        "no_case_regression": all(
            isinstance(candidate_cases.get(case_id), dict)
            and candidate_cases[case_id].get("all_repetitions_passed") is True
            for case_id in previously_stable_cases
        ),
        "success_rate": (
            candidate_rate - baseline_rate >= -thresholds.max_success_rate_drop
        ),
        "median_tokens": (
            token_change is not None
            and token_change <= thresholds.max_median_token_increase
        ),
        "p90_latency": (
            latency_change is not None
            and latency_change <= thresholds.max_p90_latency_increase
        ),
        "duplicate_tool_ratio": (
            candidate_duplicate - baseline_duplicate
            <= thresholds.max_duplicate_tool_ratio_increase
        ),
        "failed_tool_ratio": (
            candidate_failed - baseline_failed
            <= thresholds.max_failed_tool_ratio_increase
        ),
    }
    failed = tuple(name for name, value in checks.items() if not value)
    return ComparisonResult(
        passed=not failed,
        checks=checks,
        deltas={
            "success_rate_points": candidate_rate - baseline_rate,
            "median_token_relative": token_change,
            "p90_latency_relative": latency_change,
            "duplicate_tool_ratio_points": candidate_duplicate - baseline_duplicate,
            "failed_tool_ratio_points": candidate_failed - baseline_failed,
        },
        failed_checks=failed,
    )


def load_summary(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Benchmark summary must contain a JSON object")
    return value
