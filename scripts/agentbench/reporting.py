"""Reproducible JSON, Markdown and JUnit reports for AgentBench."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
from typing import Any
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict

from scripts.agentbench.schema import DatasetManifest, Verdict, public_manifest_summary
from scripts.agentbench.scoring import (
    TrialScore,
    TrialTrace,
    duplicate_tool_call_ratio,
    failed_tool_call_ratio,
)
from scripts.agentbench.statistics import distribution, wilson_interval


class TrialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    category: str
    capability: str
    repetition: int
    trace: TrialTrace
    score: TrialScore


def _git(command: str) -> str:
    completed = subprocess.run(
        ["git", *command.split()],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def environment_evidence(*, model: str | None, api_base: str | None) -> dict[str, Any]:
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "git_commit": _git("rev-parse HEAD"),
        "git_branch": _git("branch --show-current"),
        "git_status_sha256": hashlib.sha256(
            _git("status --short").encode("utf-8")
        ).hexdigest(),
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "model_alias": model,
        "api_base": api_base,
        "ci": bool(os.getenv("CI")),
    }


def summarize(
    manifest: DatasetManifest,
    records: tuple[TrialRecord, ...],
) -> dict[str, Any]:
    scored = [
        record for record in records if record.score.verdict is not Verdict.UNSCORED
    ]
    passed = [record for record in scored if record.score.passed]
    unscored = [
        record for record in records if record.score.verdict is Verdict.UNSCORED
    ]
    lower, upper = wilson_interval(len(passed), len(scored))
    category_records: dict[str, list[TrialRecord]] = defaultdict(list)
    case_records: dict[str, list[TrialRecord]] = defaultdict(list)
    for record in records:
        category_records[record.category].append(record)
        case_records[record.case_id].append(record)
    priced_costs = [
        record.trace.cost_usd
        for record in records
        if record.trace.cost_usd is not None
    ]

    def group_summary(items: list[TrialRecord]) -> dict[str, Any]:
        group_scored = [
            item for item in items if item.score.verdict is not Verdict.UNSCORED
        ]
        group_passed = sum(item.score.passed for item in group_scored)
        return {
            "trials": len(items),
            "scored": len(group_scored),
            "passed": group_passed,
            "success_rate": group_passed / len(group_scored) if group_scored else None,
            "all_repetitions_passed": bool(group_scored)
            and group_passed == len(group_scored),
        }

    return {
        "dataset": public_manifest_summary(manifest),
        "trials": len(records),
        "scored_trials": len(scored),
        "passed_trials": len(passed),
        "unscored_trials": len(unscored),
        "success_rate": len(passed) / len(scored) if scored else None,
        "wilson_95_ci": [lower, upper],
        "safety_veto_count": sum(record.score.safety_veto for record in records),
        "latency_ms": distribution(record.trace.latency_ms for record in records),
        "turn_latency_ms": distribution(
            record.trace.turn_latency_ms for record in records
        ),
        "tool_latency_ms": distribution(
            record.trace.tool_latency_ms for record in records
        ),
        "tokens": distribution(record.trace.token_count for record in records),
        "input_tokens": distribution(record.trace.input_tokens for record in records),
        "output_tokens": distribution(record.trace.output_tokens for record in records),
        "cost_usd": distribution(priced_costs) if priced_costs else None,
        "cost_usd_available_trials": len(priced_costs),
        "tool_calls": distribution(len(record.trace.tools) for record in records),
        "duplicate_tool_call_ratio": distribution(
            duplicate_tool_call_ratio(record.trace) for record in records
        ),
        "failed_tool_call_ratio": distribution(
            failed_tool_call_ratio(record.trace) for record in records
        ),
        "plans": {
            "created_trials": sum(record.trace.plan.exists for record in records),
            "stable_step_id_trials": sum(
                record.trace.plan.exists and record.trace.plan.stable_step_ids
                for record in records
            ),
            "skipped_steps": sum(record.trace.plan.skipped_steps for record in records),
            "blocked_steps": sum(record.trace.plan.blocked_steps for record in records),
        },
        "provider_retry_total": sum(
            record.trace.provider_retries for record in records
        ),
        "repair_attempt_total": sum(record.trace.repair_attempts for record in records),
        "failed_checks": dict(
            Counter(check for record in scored for check in record.score.failed_checks)
        ),
        "by_category": {
            key: group_summary(value) for key, value in sorted(category_records.items())
        },
        "by_case": {
            key: group_summary(value) for key, value in sorted(case_records.items())
        },
    }


def _json_write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_reports(
    output_dir: Path,
    *,
    manifest: DatasetManifest,
    records: tuple[TrialRecord, ...],
    environment: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = summarize(manifest, records)
    _json_write(output_dir / "environment.json", environment)
    _json_write(output_dir / "dataset-summary.json", public_manifest_summary(manifest))
    _json_write(
        output_dir / "trials.json",
        [record.model_dump(mode="json") for record in records],
    )
    _json_write(output_dir / "summary.json", summary)

    lines = [
        "# DBFox AgentBench report",
        "",
        f"- Dataset: `{manifest.dataset_id}` v{manifest.dataset_version} ({manifest.role.value})",
        f"- Commit: `{environment.get('git_commit')}`",
        f"- Passed / scored trials: {summary['passed_trials']}/{summary['scored_trials']}",
        f"- Unscored infrastructure trials: {summary['unscored_trials']}",
        f"- Safety vetoes: {summary['safety_veto_count']}",
        f"- Wilson 95% CI: {summary['wilson_95_ci'][0]:.1%}–{summary['wilson_95_ci'][1]:.1%}",
        f"- Median / p90 latency: {summary['latency_ms']['median']:.0f} / {summary['latency_ms']['p90']:.0f} ms",
        f"- Median / p90 tokens: {summary['tokens']['median']:.0f} / {summary['tokens']['p90']:.0f}",
        f"- Median / p90 tool calls: {summary['tool_calls']['median']:.1f} / {summary['tool_calls']['p90']:.1f}",
        f"- Median duplicate / failed tool ratio: {summary['duplicate_tool_call_ratio']['median']:.1%} / {summary['failed_tool_call_ratio']['median']:.1%}",
        f"- Plans observed: {summary['plans']['created_trials']}; skipped steps: {summary['plans']['skipped_steps']}",
        "",
        "## Capability groups",
        "",
        "| Category | Passed | Scored | Trials | All repetitions |",
        "|---|---:|---:|---:|---|",
    ]
    for category, item in summary["by_category"].items():
        lines.append(
            f"| {category} | {item['passed']} | {item['scored']} | {item['trials']} | "
            f"{'yes' if item['all_repetitions_passed'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Safety failures are non-compensable vetoes. Infrastructure failures are unscored, "
            "not silently counted as model failures or passes. A confidence interval over this "
            "dataset is not a universal reliability claim. Prompts, golden SQL and secrets are "
            "intentionally absent from this report.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    suite = ElementTree.Element(
        "testsuite",
        name=manifest.dataset_id,
        tests=str(len(records)),
        failures=str(sum(record.score.verdict is Verdict.FAIL for record in records)),
        skipped=str(
            sum(record.score.verdict is Verdict.UNSCORED for record in records)
        ),
    )
    for record in records:
        test_case = ElementTree.SubElement(
            suite,
            "testcase",
            classname=f"agentbench.{record.category}",
            name=f"{record.case_id}[{record.repetition}]",
            time=f"{record.trace.latency_ms / 1000:.6f}",
        )
        if record.score.verdict is Verdict.FAIL:
            failure = ElementTree.SubElement(
                test_case, "failure", message=";".join(record.score.failed_checks)
            )
            failure.text = json.dumps(record.score.checks, ensure_ascii=False)
        elif record.score.verdict is Verdict.UNSCORED:
            ElementTree.SubElement(
                test_case,
                "skipped",
                message=record.score.infrastructure_reason or "infrastructure failure",
            )
    ElementTree.ElementTree(suite).write(
        output_dir / "junit.xml",
        encoding="utf-8",
        xml_declaration=True,
    )
    return summary
