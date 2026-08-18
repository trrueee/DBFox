"""Offline contracts for the thin AgentBench Memory paired orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from scripts.agentbench.memory_paired import (
    ChildResult,
    abba_schedule,
    child_command,
    replay_memory_paired,
    run_memory_paired,
)
from scripts.agentbench.reporting import MemoryTrialEvidence, TrialRecord
from scripts.agentbench.runtime import _classify_memory_evidence, _prior_run_preflight_error
from scripts.agentbench.schema import load_manifest
from scripts.agentbench.scoring import correction_obeyed, score_trial, task_correct, TrialScore, TrialTrace
from scripts.agentbench.schema import Verdict


DATASET = Path("scripts/agentbench/datasets/memory-v1.json")
CANDIDATE_DATASET = Path("scripts/agentbench/datasets/memory-candidate-v1.json")


class _RunStatus:
    def __init__(self, status: str) -> None:
        self.status = status


def _record(
    case_id: str,
    variant: Literal["v3", "v4"],
    *,
    classification: Literal[
        "scored", "runtime_defect", "infrastructure", "model_behavior", "efficiency_regression"
    ] = "scored",
) -> TrialRecord:
    evidence = MemoryTrialEvidence(
        case_id=case_id,
        memory_variant=variant,
        projection_written=True,
        projection_typed_valid=True,
        projection_fingerprint_valid=True,
        projection_consumed=variant == "v4",
        projection_watermark=1,
        projection_lag=0,
        scope_match=True,
        generation_match=True,
        catalog_revision_match=True,
        run2_schema_search_calls=0,
        run2_schema_inspect_calls=0,
        run2_discovery_calls=0,
        duplicate_discovery_calls=0,
        stale_reuse_count=0,
        expected_memory_consumption="required",
        classification=classification,
    )
    return TrialRecord(
        case_id=case_id,
        category="memory",
        capability="test",
        repetition=1,
        trace=TrialTrace(terminal_status="completed", turn_count=2, token_count=10, latency_ms=5),
        score=TrialScore(
            verdict=Verdict.PASS,
            passed=True,
            safety_veto=False,
            checks={},
            failed_checks=(),
        ),
        memory_evidence=evidence,
    )


def _write_child(output: Path, record: TrialRecord) -> None:
    output.mkdir(parents=True)
    (output / "trials.json").write_text(
        json.dumps([record.model_dump(mode="json")]), encoding="utf-8"
    )
    (output / "environment.json").write_text(
        json.dumps({"git_commit": "commit", "model_alias": "model", "api_base": "https://provider.example/v1"}),
        encoding="utf-8",
    )


def test_memory_paired_uses_fixed_abba_schedule() -> None:
    assert abba_schedule(("case-one", "case-two", "case-three")) == (
        ("case-one", 1, "v3"),
        ("case-one", 2, "v4"),
        ("case-one", 3, "v4"),
        ("case-one", 4, "v3"),
        ("case-two", 1, "v4"),
        ("case-two", 2, "v3"),
        ("case-two", 3, "v3"),
        ("case-two", 4, "v4"),
        ("case-three", 1, "v3"),
        ("case-three", 2, "v4"),
        ("case-three", 3, "v4"),
        ("case-three", 4, "v3"),
    )


def test_memory_paired_child_command_has_no_credentials() -> None:
    command = child_command(
        dataset=DATASET, case_id="memory-schema-reuse", output=Path("trial")
    )
    assert command[:4] == [command[0], "-m", "scripts.agentbench", "real"]
    assert all("KEY" not in item.upper() and "SECRET" not in item.upper() for item in command)
    assert "--repetitions" in command and command[command.index("--repetitions") + 1] == "1"


def test_memory_paired_isolates_variants_and_aggregates(tmp_path: Path) -> None:
    seen: list[tuple[list[str], dict[str, str]]] = []

    def child(command: list[str], environment: dict[str, str]) -> ChildResult:
        seen.append((command, environment))
        case_id = command[command.index("--case") + 1]
        output = Path(command[command.index("--output") + 1])
        variant: Literal["v3", "v4"] = "v4" if environment["DBFOX_MEMORY_V4_CONTEXT"] == "1" else "v3"
        _write_child(output, _record(case_id, variant))
        return ChildResult(returncode=0, process_id=len(seen))

    summary, exit_code = run_memory_paired(
        manifest=load_manifest(DATASET),
        dataset=DATASET,
        profile="smoke",
        output=tmp_path / "paired",
        environment={"DBFOX_RUN_REAL_LLM": "1", "DBFOX_REAL_LLM_API_KEY": "not-in-argv"},
        child_runner=child,
    )

    assert exit_code == 0
    assert summary["executed_trials"] == 12
    assert [item[1]["DBFOX_MEMORY_V4_CONTEXT"] for item in seen] == [
        "0", "1", "1", "0", "1", "0", "0", "1", "0", "1", "1", "0"
    ]
    outputs = [command[command.index("--output") + 1] for command, _env in seen]
    assert len(outputs) == len(set(outputs)) == 12
    assert all("not-in-argv" not in item for command, _env in seen for item in command)
    rows = json.loads((tmp_path / "paired" / "memory-paired-trials.json").read_text())
    assert len(rows) == 12
    assert rows[0]["projection_written"] is True
    assert rows[0]["projection_consumed"] is False  # v3 shadow projection is not consumption.
    assert rows[1]["projection_consumed"] is True
    assert (tmp_path / "paired" / "memory-paired-report.md").is_file()


def test_memory_paired_stops_on_runtime_defect(tmp_path: Path) -> None:
    calls = 0

    def child(command: list[str], environment: dict[str, str]) -> ChildResult:
        nonlocal calls
        calls += 1
        case_id = command[command.index("--case") + 1]
        output = Path(command[command.index("--output") + 1])
        variant: Literal["v3", "v4"] = "v4" if environment["DBFOX_MEMORY_V4_CONTEXT"] == "1" else "v3"
        _write_child(output, _record(case_id, variant, classification="runtime_defect"))
        return ChildResult(returncode=1, process_id=1)

    summary, exit_code = run_memory_paired(
        manifest=load_manifest(DATASET), dataset=DATASET, profile="smoke",
        output=tmp_path / "paired", environment={}, child_runner=child,
    )
    assert exit_code == 1
    assert calls == 1
    assert summary["stopped_reason"] == "runtime_defect"


def test_memory_paired_stops_after_two_infrastructure_failures(tmp_path: Path) -> None:
    def child(_command: list[str], _environment: dict[str, str]) -> ChildResult:
        return ChildResult(returncode=2, process_id=1)

    summary, exit_code = run_memory_paired(
        manifest=load_manifest(DATASET), dataset=DATASET, profile="smoke",
        output=tmp_path / "paired", environment={}, child_runner=child,
    )
    assert exit_code == 1
    assert summary["executed_trials"] == 2
    assert summary["infrastructure_unscored_count"] == 2
    assert summary["stopped_reason"] == "consecutive_infrastructure_failures"


def test_memory_paired_rejects_missing_evidence(tmp_path: Path) -> None:
    def child(command: list[str], _environment: dict[str, str]) -> ChildResult:
        output = Path(command[command.index("--output") + 1])
        record = _record("memory-schema-reuse", "v3").model_copy(
            update={"memory_evidence": None}
        )
        _write_child(output, record)
        return ChildResult(returncode=0, process_id=1)

    summary, exit_code = run_memory_paired(
        manifest=load_manifest(DATASET), dataset=DATASET, profile="smoke",
        output=tmp_path / "paired", environment={}, child_runner=child,
    )
    assert exit_code == 1
    assert summary["stopped_reason"] == "invalid_child_evidence"


def test_memory_preflight_requires_only_the_prior_run_to_be_settled() -> None:
    assert _prior_run_preflight_error(
        [_RunStatus("completed"), _RunStatus("waiting_input")]
    ) is None
    assert _prior_run_preflight_error(
        [_RunStatus("waiting_input"), _RunStatus("completed")]
    ) == "prior_run_not_terminal"


def test_waiting_input_in_run_two_is_model_behavior_not_runtime_defect() -> None:
    case = load_manifest(DATASET).cases[0]
    evidence = _record(case.case_id, "v4").memory_evidence
    assert evidence is not None
    score = _semantic_score(
        failed=("terminal_status", "nonempty_answer", "required_terms", "required_numbers")
    )
    classified = _classify_memory_evidence(
        evidence,
        case=case,
        trace=TrialTrace(terminal_status="waiting_input"),
        score=score,
    )
    assert classified is not None
    assert classified.classification == "model_behavior"


def _semantic_score(*, failed: tuple[str, ...] = (), safety_veto: bool = False) -> TrialScore:
    checks = {
        "nonempty_answer": True,
        "required_terms": True,
        "any_of_terms": True,
        "forbidden_terms": True,
        "required_numbers": True,
        "citation_syntax": True,
        "citations_resolve": True,
        "min_citations": True,
        "generated_result_available": True,
        "golden_result_available": True,
        "result_equivalent": True,
    }
    checks.update({name: False for name in failed})
    return TrialScore(
        verdict=Verdict.PASS if not failed and not safety_veto else Verdict.FAIL,
        passed=not failed and not safety_veto,
        safety_veto=safety_veto,
        checks=checks,
        failed_checks=failed,
    )


def test_task_correct_is_independent_of_budget_and_trajectory_gates() -> None:
    manifest = load_manifest(DATASET)
    case = manifest.cases[0]
    budget_only = _semantic_score(failed=("token_budget",))
    trajectory_only = _semantic_score(failed=("required_tools",))
    assert task_correct(case, budget_only) is True
    assert budget_only.passed is False
    assert task_correct(case, trajectory_only) is True
    assert trajectory_only.passed is False


def test_task_correct_rejects_wrong_result_and_safety_remains_independent() -> None:
    case = load_manifest(DATASET).cases[0]
    wrong_result = _semantic_score(failed=("result_equivalent",))
    safety_failure = _semantic_score(safety_veto=True)
    assert task_correct(case, wrong_result) is False
    assert task_correct(case, safety_failure) is True
    assert safety_failure.safety_veto is True
    assert safety_failure.passed is False


def test_correction_obedience_ignores_tool_and_budget_gates() -> None:
    correction_case = load_manifest(DATASET).cases[1]
    candidate_correction_case = load_manifest(CANDIDATE_DATASET).cases[1]
    ordinary_case = load_manifest(CANDIDATE_DATASET).cases[0]
    compliant = _semantic_score(failed=("required_tools", "token_budget"))
    rejected = _semantic_score(failed=("forbidden_terms",))
    wrong_result = _semantic_score(failed=("result_equivalent",))
    assert task_correct(correction_case, compliant) is True
    assert compliant.passed is False
    assert correction_obeyed(correction_case, compliant) is True
    assert correction_obeyed(candidate_correction_case, compliant) is True
    assert correction_obeyed(ordinary_case, compliant) is None
    assert correction_obeyed(correction_case, rejected) is False
    assert correction_obeyed(correction_case, wrong_result) is False


def test_paired_summary_separates_task_correctness_from_overall_gate(tmp_path: Path) -> None:
    def child(command: list[str], environment: dict[str, str]) -> ChildResult:
        case_id = command[command.index("--case") + 1]
        output = Path(command[command.index("--output") + 1])
        variant: Literal["v3", "v4"] = "v4" if environment["DBFOX_MEMORY_V4_CONTEXT"] == "1" else "v3"
        record = _record(case_id, variant, classification="efficiency_regression").model_copy(
            update={"score": _semantic_score(failed=("token_budget",))}
        )
        _write_child(output, record)
        return ChildResult(returncode=1, process_id=1)

    summary, exit_code = run_memory_paired(
        manifest=load_manifest(DATASET), dataset=DATASET, profile="smoke",
        output=tmp_path / "paired", environment={}, child_runner=child,
    )
    assert exit_code == 0
    assert summary["v3_task_correctness"] == {"passed": 6, "valid": 6}
    assert summary["v4_task_correctness"] == {"passed": 6, "valid": 6}
    assert summary["v3_overall_gate"] == {"passed": 0, "valid": 6}
    assert summary["v4_overall_gate"] == {"passed": 0, "valid": 6}


def test_candidate_profile_runs_three_abba_blocks(tmp_path: Path) -> None:
    calls = 0

    def child(command: list[str], environment: dict[str, str]) -> ChildResult:
        nonlocal calls
        calls += 1
        case_id = command[command.index("--case") + 1]
        output = Path(command[command.index("--output") + 1])
        variant: Literal["v3", "v4"] = "v4" if environment["DBFOX_MEMORY_V4_CONTEXT"] == "1" else "v3"
        _write_child(output, _record(case_id, variant))
        return ChildResult(returncode=0, process_id=calls)

    summary, exit_code = run_memory_paired(
        manifest=load_manifest(CANDIDATE_DATASET), dataset=CANDIDATE_DATASET,
        profile="candidate", output=tmp_path / "candidate", environment={}, child_runner=child,
    )
    assert exit_code == 0
    assert calls == 96
    assert summary["planned_trials"] == summary["executed_trials"] == 96


def test_memory_paired_replay_is_deterministic_and_repairs_only_correction_evidence(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(DATASET)
    case_by_id = {case.case_id: case for case in manifest.cases}

    def child(command: list[str], environment: dict[str, str]) -> ChildResult:
        case = case_by_id[command[command.index("--case") + 1]]
        output = Path(command[command.index("--output") + 1])
        variant: Literal["v3", "v4"] = "v4" if environment["DBFOX_MEMORY_V4_CONTEXT"] == "1" else "v3"
        trace = TrialTrace(terminal_status="completed", answer="pending 200")
        score = score_trial(case, trace)
        record = _record(case.case_id, variant).model_copy(
            update={
                "trace": trace,
                "score": score,
                "memory_evidence": _record(case.case_id, variant).memory_evidence.model_copy(
                    update={"result_equivalent": score.checks.get("result_equivalent")}
                ),
            }
        )
        _write_child(output, record)
        return ChildResult(returncode=0, process_id=1)

    source = tmp_path / "source"
    run_memory_paired(
        manifest=manifest, dataset=DATASET, profile="smoke", output=source,
        environment={}, child_runner=child,
    )
    first_summary, first_gate = replay_memory_paired(
        manifest=manifest,
        source_rows_path=source / "memory-paired-trials.json",
        children=source / "children",
        source_real_workflow_run_id="workflow",
        output=tmp_path / "replay-one",
    )
    _second_summary, second_gate = replay_memory_paired(
        manifest=manifest,
        source_rows_path=source / "memory-paired-trials.json",
        children=source / "children",
        source_real_workflow_run_id="workflow",
        output=tmp_path / "replay-two",
    )
    first_provenance = json.loads(
        (tmp_path / "replay-one" / "memory-candidate-replay-provenance.json").read_text()
    )
    second_provenance = json.loads(
        (tmp_path / "replay-two" / "memory-candidate-replay-provenance.json").read_text()
    )
    replayed = json.loads(
        (tmp_path / "replay-one" / "memory-candidate-replayed-trials.json").read_text()
    )
    assert first_summary["executed_trials"] == 12
    assert first_gate == second_gate
    assert first_provenance["corrected_trials_sha256"] == second_provenance["corrected_trials_sha256"]
    assert first_provenance["provider_calls_made"] == 0
    assert all(row["correction_obeyed"] is None for row in replayed if row["case_id"] != "memory-user-correction")
    assert all(row["correction_obeyed"] is False for row in replayed if row["case_id"] == "memory-user-correction")
