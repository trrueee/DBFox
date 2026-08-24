"""Reproducible reports for the agent-mediated dbfox.data capability suite."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict

from verification.bench.capabilities.dbfox_data.agent.schema import (
    DatasetManifest,
    Verdict,
    public_manifest_summary,
)
from verification.bench.capabilities.dbfox_data.agent.scoring import (
    TrialScore,
    TrialTrace,
    duplicate_tool_call_ratio,
    failed_tool_call_ratio,
)
from verification.bench.framework.statistics import distribution, wilson_interval
from verification.bench.framework.reporting import environment_evidence as base_environment_evidence
from verification.bench.framework.schema import load_suite_manifest


class TrialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    category: str
    capability: str
    repetition: int
    trace: TrialTrace
    score: TrialScore


def environment_evidence(*, model: str | None, api_base: str | None) -> dict[str, Any]:
    return {
        **base_environment_evidence(),
        "model_alias": model,
        "api_base": api_base,
    }


def _efficiency_summary(records: tuple[TrialRecord, ...]) -> dict[str, Any]:
    turns = [turn for record in records for turn in record.trace.turn_efficiency]
    expected_turns = sum(record.trace.turn_count for record in records)
    schema_tokens = (
        [turn.tool_schema_tokens for turn in turns]
        if turns
        else [value for record in records for value in record.trace.tool_schema_tokens]
    )
    estimated_tokens = [
        turn.estimated_prompt_tokens
        for turn in turns
        if turn.estimated_prompt_tokens > 0
    ]
    provider_turn_input = [
        turn.provider_input_tokens for turn in turns if turn.provider_input_tokens > 0
    ]
    cached_turns = [turn for turn in turns if turn.cached_input_tokens is not None]
    cached_input = sum(int(turn.cached_input_tokens or 0) for turn in cached_turns)
    cached_denominator = sum(turn.provider_input_tokens for turn in cached_turns)

    adjacent_pairs = 0
    reused_pairs = 0
    growth_ratios: list[float] = []
    for record in records:
        hashes = [value for value in record.trace.tool_materialization_hashes if value]
        adjacent_pairs += max(0, len(hashes) - 1)
        reused_pairs += sum(
            left == right for left, right in zip(hashes, hashes[1:], strict=False)
        )
        by_run: dict[int, list[int]] = defaultdict(list)
        for turn in record.trace.turn_efficiency:
            if turn.provider_input_tokens > 0:
                by_run[turn.run_sequence].append(turn.provider_input_tokens)
        for values in by_run.values():
            if len(values) >= 2 and values[0] > 0:
                growth_ratios.append(values[-1] / values[0])

    estimated_total = sum(estimated_tokens)
    schema_total = sum(schema_tokens)
    response_item_total = sum(turn.response_item_tokens for turn in turns)
    return {
        "turn_detail_coverage": {
            "observed": len(turns),
            "expected": expected_turns,
        },
        "provider_input_tokens_total": sum(
            record.trace.input_tokens for record in records
        ),
        "provider_output_tokens_total": sum(
            record.trace.output_tokens for record in records
        ),
        "provider_input_tokens_per_turn": (
            distribution(provider_turn_input) if provider_turn_input else None
        ),
        "estimated_prompt_tokens_per_turn": (
            distribution(estimated_tokens) if estimated_tokens else None
        ),
        "tool_schema_tokens_total": schema_total,
        "tool_schema_tokens_per_turn": distribution(schema_tokens),
        "tool_schema_share_of_estimate": (
            schema_total / estimated_total if estimated_total else None
        ),
        "estimated_tool_schema_to_provider_input_ratio": (
            schema_total / sum(record.trace.input_tokens for record in records)
            if sum(record.trace.input_tokens for record in records)
            else None
        ),
        "response_item_tokens_total": response_item_total,
        "response_item_share_of_estimate": (
            response_item_total / estimated_total if estimated_total else None
        ),
        "cached_usage_coverage_turns": len(cached_turns),
        "cached_input_ratio": (
            cached_input / cached_denominator if cached_denominator else None
        ),
        "adjacent_materialization_reuse_ratio": (
            reused_pairs / adjacent_pairs if adjacent_pairs else None
        ),
        "within_run_input_growth": (
            distribution(growth_ratios) if growth_ratios else None
        ),
        "prompt_omission_turns": sum(
            bool(turn.omitted_messages or turn.omitted_response_batches)
            for turn in turns
        ),
        "prompt_truncation_turns": sum(bool(turn.truncated_messages) for turn in turns),
        "transient_tool_output_turns": sum(
            bool(turn.transient_tool_output_count) for turn in turns
        ),
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
        record.trace.cost_usd for record in records if record.trace.cost_usd is not None
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
            "turns": distribution(item.trace.turn_count for item in items),
            "input_tokens": distribution(item.trace.input_tokens for item in items),
            "tool_schema_tokens": distribution(
                sum(item.trace.tool_schema_tokens) for item in items
            ),
            "tool_calls": distribution(len(item.trace.tools) for item in items),
        }

    suite = load_suite_manifest(Path(__file__).resolve().parent / "suite.json")
    return {
        "suite": suite.public_summary(),
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
        "efficiency": _efficiency_summary(records),
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


def _optional_ratio(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "unavailable"


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
        "# DBFox dbfox.data CapabilityBench report",
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
        "## Prompt and runtime efficiency",
        "",
        f"- Per-Turn detail coverage: {summary['efficiency']['turn_detail_coverage']['observed']}/{summary['efficiency']['turn_detail_coverage']['expected']}",
        f"- Provider input / output tokens: {summary['efficiency']['provider_input_tokens_total']} / {summary['efficiency']['provider_output_tokens_total']}",
        f"- Estimated tool-schema tokens: {summary['efficiency']['tool_schema_tokens_total']}",
        f"- Tool-schema / Responses-Item share of DBFox estimate: {_optional_ratio(summary['efficiency']['tool_schema_share_of_estimate'])} / {_optional_ratio(summary['efficiency']['response_item_share_of_estimate'])}",
        f"- Prompt omission / truncation Turns: {summary['efficiency']['prompt_omission_turns']} / {summary['efficiency']['prompt_truncation_turns']}",
        f"- Provider cache detail coverage / cached-input ratio: {summary['efficiency']['cached_usage_coverage_turns']} Turns / {_optional_ratio(summary['efficiency']['cached_input_ratio'])}",
        f"- Adjacent tool-materialization reuse: {_optional_ratio(summary['efficiency']['adjacent_materialization_reuse_ratio'])}",
        "",
        "Prompt-token values are conservative DBFox estimates; provider input/output values are billing usage. Cache ratios are reported only when the provider supplies cache details. Repeated tool materialization is diagnostic evidence, not an automatic savings estimate.",
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
            "## Efficiency by case",
            "",
            "| Case | Passed | Median Turns | Median input tokens | Median estimated schema tokens | Median tools |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for case_id, item in summary["by_case"].items():
        lines.append(
            f"| {case_id} | {item['passed']}/{item['scored']} | "
            f"{item['turns']['median']:.1f} | {item['input_tokens']['median']:.0f} | "
            f"{item['tool_schema_tokens']['median']:.0f} | "
            f"{item['tool_calls']['median']:.1f} |"
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
            classname=f"capability.dbfox_data.agent.{record.category}",
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
