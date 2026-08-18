"""Thin subprocess orchestration for the Memory v4 AgentBench smoke profile."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any, Callable, Literal
from uuid import uuid4

from scripts.agentbench.reporting import TrialRecord
from scripts.agentbench.schema import DatasetManifest, EvalCase
from scripts.agentbench.scoring import correction_obeyed, score_trial, task_correct
from scripts.agentbench.statistics import percentile


Variant = Literal["v3", "v4"]
ChildRunner = Callable[[list[str], dict[str, str]], "ChildResult"]


@dataclass(frozen=True)
class ChildResult:
    returncode: int
    process_id: int | None


def abba_schedule(case_ids: tuple[str, ...]) -> tuple[tuple[str, int, Variant], ...]:
    """Return the fixed, documented ABBA positions for the smoke suite."""

    variants: tuple[tuple[Variant, ...], ...] = (
        ("v3", "v4", "v4", "v3"),
        ("v4", "v3", "v3", "v4"),
    )
    return tuple(
        (case_id, position, variant)
        for case_index, case_id in enumerate(case_ids)
        for position, variant in enumerate(variants[case_index % 2], start=1)
    )


def child_command(*, dataset: Path, case_id: str, output: Path) -> list[str]:
    """Call the existing real command; credentials never appear in argv."""

    return [
        sys.executable,
        "-m",
        "scripts.agentbench",
        "real",
        "--dataset",
        str(dataset),
        "--case",
        case_id,
        "--repetitions",
        "1",
        "--output",
        str(output),
    ]


def _run_child(command: list[str], environment: dict[str, str]) -> ChildResult:
    process = subprocess.Popen(command, env=environment)
    return ChildResult(returncode=process.wait(), process_id=process.pid)


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _median(values: list[int | float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _identity(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _read_child_record(output: Path) -> tuple[TrialRecord | None, str | None, dict[str, Any]]:
    trials_path = output / "trials.json"
    environment_path = output / "environment.json"
    environment: dict[str, Any] = {}
    if environment_path.is_file():
        loaded = json.loads(environment_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            environment = loaded
    if not trials_path.is_file():
        return None, "child_report_missing", environment
    try:
        payload = json.loads(trials_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list) or len(payload) != 1:
            return None, "child_trial_count_invalid", environment
        return TrialRecord.model_validate(payload[0]), None, environment
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "child_trial_record_invalid", environment


def _trial_row(
    *,
    case_id: str,
    position: int,
    variant: Variant,
    trial_id: str,
    process_id: int | None,
    case: EvalCase,
    record: TrialRecord | None,
    failure: str | None,
    environment: dict[str, Any],
) -> dict[str, Any]:
    evidence = record.memory_evidence if record is not None else None
    trace = record.trace if record is not None else None
    score = record.score if record is not None else None
    classification = (
        evidence.classification
        if evidence is not None
        else "infrastructure"
        if (failure == "child_report_missing" or (record and record.trace.infrastructure_error))
        else "invalid"
    )
    return {
        "case_id": case_id,
        "position": position,
        "variant": variant,
        "trial_id": trial_id,
        "child_process_id": process_id,
        "commit_sha": environment.get("git_commit"),
        "dataset_id": environment.get("dataset_id"),
        "model": environment.get("model_alias"),
        "api_base_identity": _identity(environment.get("api_base")),
        "classification": classification,
        "task_correct": task_correct(case, score) if score is not None else None,
        "overall_gate_passed": score.passed if score is not None else None,
        "safety_passed": (not score.safety_veto) if score is not None else None,
        "failed_checks": list(score.failed_checks) if score is not None else [],
        "result_equivalent": evidence.result_equivalent if evidence else None,
        "correction_obeyed": evidence.correction_obeyed if evidence else None,
        "projection_written": evidence.projection_written if evidence else None,
        "projection_consumed": evidence.projection_consumed if evidence else None,
        "scope_match": evidence.scope_match if evidence else None,
        "run2_schema_search": evidence.run2_schema_search_calls if evidence else None,
        "run2_schema_inspect": evidence.run2_schema_inspect_calls if evidence else None,
        "run2_discovery": evidence.run2_discovery_calls if evidence else None,
        "stale_reuse": evidence.stale_reuse_count if evidence else None,
        "turns": trace.turn_count if trace else None,
        "tokens": trace.token_count if trace else None,
        "latency": trace.latency_ms if trace else None,
        "projection_error_code": evidence.projection_error_code if evidence else failure,
        "child_exit_code": None if record is not None else failure,
    }


def _summary(rows: list[dict[str, Any]], *, planned: int, stopped_reason: str | None) -> dict[str, Any]:
    def values(variant: Variant, field: str) -> list[int | float]:
        return [
            value
            for row in rows
            if row["variant"] == variant
            and row["classification"] in {"scored", "model_behavior", "efficiency_regression"}
            and isinstance((value := row.get(field)), (int, float))
            and not isinstance(value, bool)
        ]

    def metric(variant: Variant, field: str) -> dict[str, int]:
        valid = [
            row for row in rows
            if row["variant"] == variant
            and row["classification"] in {"scored", "model_behavior", "efficiency_regression"}
        ]
        return {"passed": sum(row[field] is True for row in valid), "valid": len(valid)}

    def correction_metric(variant: Variant) -> dict[str, int]:
        relevant = [
            row
            for row in rows
            if row["variant"] == variant
            and row["classification"] in {"scored", "model_behavior", "efficiency_regression"}
            and row.get("correction_obeyed") is not None
        ]
        return {
            "passed": sum(row["correction_obeyed"] is True for row in relevant),
            "valid": len(relevant),
        }

    return {
        "planned_trials": planned,
        "executed_trials": len(rows),
        "stopped_reason": stopped_reason,
        "v3_valid_trials": metric("v3", "task_correct")["valid"],
        "v4_valid_trials": metric("v4", "task_correct")["valid"],
        "v3_task_correctness": metric("v3", "task_correct"),
        "v4_task_correctness": metric("v4", "task_correct"),
        "v3_overall_gate": metric("v3", "overall_gate_passed"),
        "v4_overall_gate": metric("v4", "overall_gate_passed"),
        "v3_correction_compliance": correction_metric("v3"),
        "v4_correction_compliance": correction_metric("v4"),
        "v3_run2_discovery_total": sum(values("v3", "run2_discovery")),
        "v4_run2_discovery_total": sum(values("v4", "run2_discovery")),
        "v3_median_run2_discovery": _median(values("v3", "run2_discovery")),
        "v4_median_run2_discovery": _median(values("v4", "run2_discovery")),
        "v3_median_turns": _median(values("v3", "turns")),
        "v4_median_turns": _median(values("v4", "turns")),
        "v3_median_tokens": _median(values("v3", "tokens")),
        "v4_median_tokens": _median(values("v4", "tokens")),
        "v3_median_latency": _median(values("v3", "latency")),
        "v4_median_latency": _median(values("v4", "latency")),
        "runtime_defect_count": sum(row["classification"] == "runtime_defect" for row in rows),
        "infrastructure_unscored_count": sum(row["classification"] == "infrastructure" for row in rows),
        "model_behavior_failure_count": sum(row["classification"] == "model_behavior" for row in rows),
        "efficiency_regression_count": sum(row["classification"] == "efficiency_regression" for row in rows),
    }


def _markdown(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        "# DBFox Memory paired smoke",
        "",
        f"- Planned / executed: {summary['planned_trials']}/{summary['executed_trials']}",
        f"- Runtime defects: {summary['runtime_defect_count']}",
        f"- Infrastructure exclusions: {summary['infrastructure_unscored_count']}",
        "",
        "| Case | Position | Variant | Classification | Task correct | Overall gate | Safety | Result | Correction | Consumed | Discovery | Tokens | Latency ms |",
        "|---|---:|---|---|---|---|---|---|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {case_id} | {position} | {variant} | {classification} | {task_correct} | {overall_gate_passed} | {safety_passed} | {result_equivalent} | {correction_obeyed} | {projection_consumed} | {run2_discovery} | {tokens} | {latency} |".format(**row)
        )
    lines.extend([
        "",
        "This is a pipeline smoke only. It is not a Memory v4 cutover decision.",
        "",
    ])
    return "\n".join(lines)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def _load_replay_records(children: Path) -> tuple[TrialRecord, ...]:
    paths = sorted(children.glob("*/trials.json"))
    records: list[TrialRecord] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list) or len(payload) != 1:
            raise ValueError("memory paired replay requires one TrialRecord per child")
        records.append(TrialRecord.model_validate(payload[0]))
    if not records:
        raise ValueError("memory paired replay requires child TrialRecord files")
    return tuple(records)


def _assert_row_matches_record(
    row: dict[str, Any],
    *,
    case: EvalCase,
    record: TrialRecord,
) -> None:
    evidence = record.memory_evidence
    if evidence is None:
        raise ValueError("memory paired replay requires durable Memory evidence")
    expected = {
        "case_id": record.case_id,
        "variant": evidence.memory_variant,
        "task_correct": task_correct(case, record.score),
        "overall_gate_passed": record.score.passed,
        "safety_passed": not record.score.safety_veto,
        "failed_checks": list(record.score.failed_checks),
        "result_equivalent": evidence.result_equivalent,
        "projection_written": evidence.projection_written,
        "projection_consumed": evidence.projection_consumed,
        "scope_match": evidence.scope_match,
        "run2_schema_search": evidence.run2_schema_search_calls,
        "run2_schema_inspect": evidence.run2_schema_inspect_calls,
        "run2_discovery": evidence.run2_discovery_calls,
        "stale_reuse": evidence.stale_reuse_count,
        "turns": record.trace.turn_count,
        "tokens": record.trace.token_count,
        "latency": record.trace.latency_ms,
        "projection_error_code": evidence.projection_error_code,
    }
    for field, value in expected.items():
        if row.get(field) != value:
            raise ValueError(f"memory paired replay immutable field mismatch: {field}")
    if row.get("classification") != evidence.classification:
        raise ValueError("memory paired replay immutable field mismatch: classification")


def _candidate_gate(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    correction_case_ids: frozenset[str],
) -> dict[str, Any]:
    valid = [
        row
        for row in rows
        if row["classification"] in {"scored", "model_behavior", "efficiency_regression"}
    ]
    by_variant = {
        variant: [row for row in valid if row["variant"] == variant]
        for variant in ("v3", "v4")
    }
    v3_latency = [float(row["latency"]) for row in by_variant["v3"]]
    v4_latency = [float(row["latency"]) for row in by_variant["v4"]]
    v3_tokens = float(summary["v3_median_tokens"] or 0)
    v4_tokens = float(summary["v4_median_tokens"] or 0)
    token_delta = (v4_tokens / v3_tokens - 1) if v3_tokens else None
    latency_p90_delta = (
        percentile(v4_latency, 0.90) / percentile(v3_latency, 0.90) - 1
        if v3_latency and percentile(v3_latency, 0.90)
        else None
    )
    correction_complete = all(
        row.get("correction_obeyed") is not None
        for row in rows
        if row["case_id"] in correction_case_ids
    )
    checks = {
        "runtime_defects_zero": summary["runtime_defect_count"] == 0,
        "infrastructure_exclusions_zero": summary["infrastructure_unscored_count"] == 0,
        "safety_all_passed": len(valid) == len(rows)
        and all(row["safety_passed"] is True for row in rows),
        "v4_required_consumption": bool(by_variant["v4"])
        and all(row["projection_consumed"] is True for row in by_variant["v4"]),
        "v3_did_not_consume_v4": all(
            row["projection_consumed"] is False for row in by_variant["v3"]
        ),
        "stale_reuse_zero": all(row["stale_reuse"] == 0 for row in rows),
        "task_correctness_non_regression": (
            summary["v4_task_correctness"]["passed"]
            >= summary["v3_task_correctness"]["passed"]
        ),
        "discovery_non_regression": (
            summary["v4_run2_discovery_total"]
            <= summary["v3_run2_discovery_total"]
        ),
        "token_guardrail": token_delta is not None and token_delta <= 0.15,
        "latency_guardrail": latency_p90_delta is not None and latency_p90_delta <= 0.20,
        "correction_evidence_complete": correction_complete,
        "correction_non_regression": (
            summary["v4_correction_compliance"]["passed"]
            >= summary["v3_correction_compliance"]["passed"]
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "token_delta": token_delta,
        "latency_p90_delta": latency_p90_delta,
    }


def replay_memory_paired(
    *,
    manifest: DatasetManifest,
    source_rows_path: Path,
    children: Path,
    source_real_workflow_run_id: str,
    output: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Repair derived paired evidence without rerunning a Provider or Runtime."""

    source_rows = json.loads(source_rows_path.read_text(encoding="utf-8"))
    if not isinstance(source_rows, list):
        raise ValueError("memory paired replay source rows must be a JSON list")
    records = _load_replay_records(children)
    if len(source_rows) != len(records):
        raise ValueError("memory paired replay source rows and child records differ")
    case_by_id = {case.case_id: case for case in manifest.cases}
    corrected_rows: list[dict[str, Any]] = []
    for raw_row, source_record in zip(source_rows, records, strict=True):
        if not isinstance(raw_row, dict):
            raise ValueError("memory paired replay source row is invalid")
        case = case_by_id.get(source_record.case_id)
        if case is None:
            raise ValueError("memory paired replay source case is absent from dataset")
        rescored = score_trial(case, source_record.trace)
        if rescored != source_record.score:
            raise ValueError("memory paired replay score changed outside evidence repair")
        _assert_row_matches_record(raw_row, case=case, record=source_record)
        evidence = source_record.memory_evidence
        assert evidence is not None
        corrected = dict(raw_row)
        corrected["correction_obeyed"] = correction_obeyed(case, rescored)
        corrected_rows.append(corrected)

    output.mkdir(parents=True, exist_ok=False)
    summary = _summary(
        corrected_rows,
        planned=len(source_rows),
        stopped_reason=None,
    )
    gate = _candidate_gate(
        corrected_rows,
        summary,
        correction_case_ids=frozenset(
            case.case_id for case in manifest.cases if case.correction_evidence
        ),
    )
    corrected_hash = _canonical_sha256(corrected_rows)
    source_sha = _file_sha256(source_rows_path)
    source_record_hash = _canonical_sha256(
        [record.model_dump(mode="json") for record in records]
    )
    commits = {str(row.get("commit_sha") or "") for row in source_rows}
    if len(commits) != 1 or not next(iter(commits)):
        raise ValueError("memory paired replay source has no single evaluation SHA")
    provenance = {
        "replay_mode": "offline_evidence_repair",
        "source_real_workflow_run_id": source_real_workflow_run_id,
        "source_evaluation_sha": next(iter(commits)),
        "source_trials_sha256": source_sha,
        "source_child_trials_sha256": source_record_hash,
        "evaluator_sha": _git_sha(),
        "dataset_id": manifest.dataset_id,
        "dataset_version": manifest.dataset_version,
        "corrected_trials_sha256": corrected_hash,
        "provider_calls_made": 0,
    }
    _json(output / "memory-candidate-replayed-trials.json", corrected_rows)
    _json(output / "memory-candidate-replayed-summary.json", summary)
    _json(output / "memory-candidate-replayed-gate.json", gate)
    _json(output / "memory-candidate-replay-provenance.json", provenance)
    (output / "memory-candidate-replayed-report.md").write_text(
        "# DBFox Memory candidate offline evidence repair\n\n"
        f"- Source workflow: `{source_real_workflow_run_id}`\n"
        f"- Source trials SHA-256: `{source_sha}`\n"
        f"- Corrected trials SHA-256: `{corrected_hash}`\n"
        f"- Candidate gate: `{'PASS' if gate['passed'] else 'BLOCKED'}`\n\n"
        + _markdown(corrected_rows, summary),
        encoding="utf-8",
    )
    return summary, gate


def run_memory_paired(
    *,
    manifest: DatasetManifest,
    dataset: Path,
    profile: str,
    output: Path,
    environment: dict[str, str],
    child_runner: ChildRunner = _run_child,
) -> tuple[dict[str, Any], int]:
    """Run fixed ABBA blocks, stopping immediately on a runtime defect."""

    profile_blocks = {"smoke": 1, "candidate": 3}
    blocks = profile_blocks.get(profile)
    if blocks is None:
        raise ValueError("memory-paired profile is not supported")
    if profile == "smoke" and len(manifest.cases) != 3:
        raise ValueError("memory-paired smoke requires exactly three dataset cases")
    if profile == "candidate" and not 8 <= len(manifest.cases) <= 12:
        raise ValueError("memory-paired candidate requires eight to twelve dataset cases")
    if any(case.expected_memory_consumption == "optional" for case in manifest.cases):
        raise ValueError("memory-paired cases must declare Memory consumption expectations")
    output.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    stopped_reason: str | None = None
    consecutive_infrastructure = 0
    case_by_id = {case.case_id: case for case in manifest.cases}
    schedule = abba_schedule(tuple(case.case_id for case in manifest.cases))
    for block_index in range(1, blocks + 1):
        for case_id, position, variant in schedule:
            trial_id = uuid4().hex
            child_output = output / "children" / f"{len(rows) + 1:03d}-b{block_index}-{case_id}-{variant}"
            command = child_command(dataset=dataset, case_id=case_id, output=child_output)
            child_environment = dict(environment)
            child_environment["DBFOX_MEMORY_V4_CONTEXT"] = "1" if variant == "v4" else "0"
            started_at = datetime.now(UTC).isoformat()
            result = child_runner(command, child_environment)
            completed_at = datetime.now(UTC).isoformat()
            record, read_error, child_environment_report = _read_child_record(child_output)
            if record is not None:
                evidence = record.memory_evidence
                if evidence is None and not record.trace.infrastructure_error:
                    read_error = "memory_evidence_invalid"
                    record = None
                elif evidence is not None and evidence.memory_variant != variant:
                    read_error = "memory_variant_invalid"
                    record = None
                elif record.case_id != case_id:
                    read_error = "child_case_mismatch"
                    record = None
            row = _trial_row(
                case_id=case_id,
                position=position,
                variant=variant,
                trial_id=trial_id,
                process_id=result.process_id,
                case=case_by_id[case_id],
                record=record,
                failure=read_error,
                environment=child_environment_report,
            )
            row["block_index"] = block_index
            row["dataset_id"] = manifest.dataset_id
            row["dataset_version"] = manifest.dataset_version
            row["started_at"] = started_at
            row["completed_at"] = completed_at
            if result.returncode != 0 and record is None and read_error is None:
                row["classification"] = "infrastructure"
                row["projection_error_code"] = "child_exit_nonzero"
            rows.append(row)
            if row["classification"] == "runtime_defect":
                stopped_reason = "runtime_defect"
                break
            if row["classification"] == "invalid":
                stopped_reason = "invalid_child_evidence"
                break
            if row["classification"] == "infrastructure":
                consecutive_infrastructure += 1
                if consecutive_infrastructure >= 2:
                    stopped_reason = "consecutive_infrastructure_failures"
                    break
            else:
                consecutive_infrastructure = 0
        if stopped_reason is not None:
            break
    summary = _summary(rows, planned=len(schedule) * blocks, stopped_reason=stopped_reason)
    _json(output / "memory-paired-trials.json", rows)
    _json(output / "memory-paired-summary.json", summary)
    (output / "memory-paired-report.md").write_text(
        _markdown(rows, summary), encoding="utf-8"
    )
    return summary, 0 if stopped_reason is None else 1
