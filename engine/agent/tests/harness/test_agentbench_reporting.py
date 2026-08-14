from __future__ import annotations

import json

from scripts.agentbench.reporting import TrialRecord, write_reports
from scripts.agentbench.schema import DatasetManifest
from scripts.agentbench.scoring import (
    PlanTrace,
    ToolTrace,
    TrialTrace,
    TurnEfficiencyTrace,
    score_trial,
)


def test_reports_are_reproducible_and_do_not_copy_prompts_or_golden_sql(
    tmp_path,
) -> None:
    manifest = DatasetManifest.model_validate(
        {
            "schema_version": "1.0",
            "dataset_id": "report-contract",
            "dataset_version": "1.0.0",
            "role": "regression",
            "seed_version": "seed-v1",
            "description": "report contract",
            "cases": [
                {
                    "case_id": "report-case",
                    "category": "reporting",
                    "capability": "redacted evidence",
                    "prompts": ["PRIVATE PROMPT SENTINEL"],
                    "answer": {"required_numbers": [3]},
                    "result": {"golden_sql": "SELECT 3 AS GOLDEN_SENTINEL"},
                    "trace": {"require_valid_citations": False},
                }
            ],
        }
    )
    case = manifest.cases[0]
    trace = TrialTrace(
        terminal_status="completed",
        answer="结果是 3。",
        turn_count=1,
        token_count=10,
        input_tokens=7,
        output_tokens=3,
        cost_usd=0.01,
        latency_ms=20,
        turn_latency_ms=18,
        tool_latency_ms=4,
        tool_materialization_hashes=("same", "same"),
        turn_efficiency=(
            TurnEfficiencyTrace(
                run_sequence=1,
                turn_sequence=1,
                provider_input_tokens=7,
                provider_output_tokens=3,
                cached_input_tokens=2,
                estimated_prompt_tokens=8,
                max_prompt_tokens=100,
                message_tokens=3,
                reserved_tokens=5,
                tool_schema_count=2,
                tool_schema_tokens=4,
                response_item_tokens=1,
                transient_tool_output_count=1,
            ),
        ),
        tools=(
            ToolTrace(
                name="sql_execute_readonly",
                status="succeeded",
                input_hash="input-1",
                latency_ms=4,
            ),
        ),
        plan=PlanTrace(
            exists=True,
            version_count=2,
            terminal_status="completed",
            step_count=1,
            completed_steps=1,
        ),
        generated_result={"columns": ["GOLDEN_SENTINEL"], "rows": [[3]]},
        golden_result={"columns": ["GOLDEN_SENTINEL"], "rows": [[3]]},
    )
    record = TrialRecord(
        case_id=case.case_id,
        category=case.category,
        capability=case.capability,
        repetition=1,
        trace=trace,
        score=score_trial(case, trace),
    )
    output = tmp_path / "report"
    summary = write_reports(
        output,
        manifest=manifest,
        records=(record,),
        environment={"git_commit": "fixture"},
    )
    assert summary["passed_trials"] == 1
    assert summary["input_tokens"]["median"] == 7
    assert summary["output_tokens"]["median"] == 3
    assert summary["cost_usd"]["median"] == 0.01
    assert summary["cost_usd_available_trials"] == 1
    assert summary["plans"]["created_trials"] == 1
    assert summary["efficiency"]["turn_detail_coverage"] == {
        "observed": 1,
        "expected": 1,
    }
    assert summary["efficiency"]["tool_schema_share_of_estimate"] == 0.5
    assert summary["efficiency"]["cached_input_ratio"] == 2 / 7
    assert summary["efficiency"]["transient_tool_output_turns"] == 1
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.iterdir()
        if path.suffix in {".json", ".md", ".xml"}
    )
    assert "PRIVATE PROMPT SENTINEL" not in combined
    assert "SELECT 3 AS GOLDEN_SENTINEL" not in combined
    assert "Passed / scored trials: 1/1" in (output / "report.md").read_text(
        encoding="utf-8"
    )
    junit = (output / "junit.xml").read_text(encoding="utf-8")
    assert 'tests="1"' in junit
    json.loads((output / "summary.json").read_text(encoding="utf-8"))


def test_report_marks_cost_unavailable_instead_of_claiming_zero(tmp_path) -> None:
    manifest = DatasetManifest.model_validate(
        {
            "schema_version": "1.0",
            "dataset_id": "unpriced-contract",
            "dataset_version": "1.0.0",
            "role": "regression",
            "seed_version": "seed-v1",
            "description": "unpriced contract",
            "cases": [
                {
                    "case_id": "unpriced-case",
                    "category": "reporting",
                    "capability": "unknown price",
                    "prompts": ["private"],
                    "trace": {"require_valid_citations": False},
                }
            ],
        }
    )
    case = manifest.cases[0]
    trace = TrialTrace(
        terminal_status="completed",
        answer="done",
        input_tokens=100,
        output_tokens=20,
        cost_usd=None,
    )
    record = TrialRecord(
        case_id=case.case_id,
        category=case.category,
        capability=case.capability,
        repetition=1,
        trace=trace,
        score=score_trial(case, trace),
    )

    summary = write_reports(
        tmp_path / "unpriced",
        manifest=manifest,
        records=(record,),
        environment={"git_commit": "fixture"},
    )

    assert summary["cost_usd"] is None
    assert summary["cost_usd_available_trials"] == 0
