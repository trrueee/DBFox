"""Offline contracts for the thin AgentBench Memory paired orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from scripts.agentbench.memory_paired import (
    ChildResult,
    abba_schedule,
    child_command,
    run_memory_paired,
)
from scripts.agentbench.reporting import MemoryTrialEvidence, TrialRecord
from scripts.agentbench.schema import load_manifest
from scripts.agentbench.scoring import TrialScore, TrialTrace
from scripts.agentbench.schema import Verdict


DATASET = Path("scripts/agentbench/datasets/memory-v1.json")


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
