"""Domain-neutral JSON and Markdown reporting for benchmark outcomes."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
from typing import Any

from verification.bench.framework.schema import SuiteManifest
from verification.bench.framework.statistics import distribution, wilson_interval
from verification.bench.framework.trial import TrialOutcome


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def environment_evidence() -> dict[str, Any]:
    status = _git("status", "--short")
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_branch": _git("branch", "--show-current"),
        "git_status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "ci": bool(os.getenv("CI")),
    }


def summarize_outcomes(
    manifest: SuiteManifest,
    outcomes: tuple[TrialOutcome, ...],
) -> dict[str, Any]:
    invalid_suites = {item.suite_id for item in outcomes} - {manifest.suite_id}
    if invalid_suites:
        raise ValueError(f"Trial outcomes belong to another suite: {invalid_suites}")
    scored = [item for item in outcomes if item.verdict != "unscored"]
    passed = [item for item in scored if item.verdict == "pass"]
    lower, upper = wilson_interval(len(passed), len(scored))
    metrics: dict[str, list[float]] = defaultdict(list)
    for item in outcomes:
        for name, value in item.metrics.items():
            metrics[name].append(value)
    declared = {item.name for item in manifest.metrics}
    undeclared = set(metrics) - declared
    if undeclared:
        raise ValueError(f"Trials emitted undeclared metrics: {sorted(undeclared)}")
    return {
        "suite": manifest.public_summary(),
        "trials": len(outcomes),
        "scored_trials": len(scored),
        "passed_trials": len(passed),
        "unscored_trials": len(outcomes) - len(scored),
        "success_rate": len(passed) / len(scored) if scored else None,
        "wilson_95_ci": [lower, upper],
        "metrics": {
            name: distribution(values) for name, values in sorted(metrics.items())
        },
        "failed_checks": sorted(
            {check for item in outcomes for check in item.failed_checks}
        ),
    }


def write_suite_report(
    output_dir: Path,
    *,
    manifest: SuiteManifest,
    outcomes: tuple[TrialOutcome, ...],
    environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = summarize_outcomes(manifest, outcomes)
    payloads = {
        "environment.json": environment or environment_evidence(),
        "suite.json": manifest.public_summary(),
        "trials.json": [item.model_dump(mode="json") for item in outcomes],
        "summary.json": summary,
    }
    for name, payload in payloads.items():
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    lines = [
        f"# {manifest.suite_id} benchmark report",
        "",
        f"- Subject: `{manifest.subject.kind.value}` / {', '.join(manifest.subject.components)}",
        f"- Passed / scored trials: {summary['passed_trials']}/{summary['scored_trials']}",
        f"- Unscored trials: {summary['unscored_trials']}",
        "",
        "## Metrics",
        "",
        "| Metric | Median | p90 | Maximum |",
        "|---|---:|---:|---:|",
    ]
    for name, values in summary["metrics"].items():
        lines.append(
            f"| {name} | {values['median']:.3f} | {values['p90']:.3f} | {values['maximum']:.3f} |"
        )
    lines.extend(
        [
            "",
            "The suite subject owns score interpretation. Supporting fixtures are not the subject under test.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary
