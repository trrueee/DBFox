"""Capability-neutral paired comparison over declared suite metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComparisonThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_success_rate_drop: float = Field(default=0.03, ge=0, le=1)
    max_relative_metric_regression: float = Field(default=0.20, ge=0)


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    checks: dict[str, bool]
    deltas: dict[str, float | None]
    failed_checks: tuple[str, ...]


def _relative_change(baseline: float, candidate: float) -> float | None:
    if baseline == 0:
        return 0.0 if candidate == 0 else None
    return (candidate - baseline) / abs(baseline)


def compare_summaries(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    thresholds: ComparisonThresholds = ComparisonThresholds(),
) -> ComparisonResult:
    baseline_suite = baseline.get("suite") or {}
    candidate_suite = candidate.get("suite") or {}
    directions = {
        str(item.get("name")): str(item.get("direction"))
        for item in candidate_suite.get("metrics") or []
        if isinstance(item, dict)
    }
    baseline_metrics = baseline.get("metrics") or {}
    candidate_metrics = candidate.get("metrics") or {}
    checks = {
        "same_suite": (
            baseline_suite.get("suite_id") == candidate_suite.get("suite_id")
            and baseline_suite.get("suite_version")
            == candidate_suite.get("suite_version")
        ),
        "candidate_has_scored_trials": int(candidate.get("scored_trials") or 0) > 0,
        "no_new_infrastructure_failures": int(candidate.get("unscored_trials") or 0)
        <= int(baseline.get("unscored_trials") or 0),
        "success_rate": float(candidate.get("success_rate") or 0)
        - float(baseline.get("success_rate") or 0)
        >= -thresholds.max_success_rate_drop,
        "same_metric_set": set(baseline_metrics) == set(candidate_metrics) == set(directions),
    }
    deltas: dict[str, float | None] = {
        "success_rate_points": float(candidate.get("success_rate") or 0)
        - float(baseline.get("success_rate") or 0)
    }
    if checks["same_metric_set"]:
        for name, direction in directions.items():
            baseline_value = float((baseline_metrics[name] or {}).get("median") or 0)
            candidate_value = float((candidate_metrics[name] or {}).get("median") or 0)
            change = _relative_change(baseline_value, candidate_value)
            deltas[name] = change
            if direction == "lower_is_better":
                passed = (
                    candidate_value <= baseline_value
                    if baseline_value == 0
                    else change is not None
                    and change <= thresholds.max_relative_metric_regression
                )
            elif direction == "higher_is_better":
                passed = (
                    candidate_value >= baseline_value
                    if baseline_value == 0
                    else change is not None
                    and change >= -thresholds.max_relative_metric_regression
                )
            elif direction == "zero_is_best":
                passed = candidate_value <= baseline_value
            else:
                passed = True
            checks[f"metric:{name}"] = passed
    failed = tuple(name for name, value in checks.items() if not value)
    return ComparisonResult(
        passed=not failed,
        checks=checks,
        deltas=deltas,
        failed_checks=failed,
    )


def load_summary(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Benchmark summary must contain a JSON object")
    return value
