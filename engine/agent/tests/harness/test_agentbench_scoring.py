from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.agent.evidence import citation_references
from scripts.agentbench.calibration import load_calibration, run_calibration
from scripts.agentbench.schema import ComparisonMode, DatasetManifest
from scripts.agentbench.scoring import (
    PlanTrace,
    ResultTable,
    RunTrace,
    ToolTrace,
    TrialTrace,
    duplicate_tool_call_ratio,
    failed_tool_call_ratio,
    result_sets_equivalent,
    score_trial,
)
from scripts.agentbench.statistics import distribution, wilson_interval
from scripts.agentbench.runtime import _infrastructure_reason, _select_generated_query


ROOT = Path(__file__).resolve().parents[4]


def test_agentbench_scorer_calibration_is_perfect() -> None:
    suite = load_calibration(
        ROOT / "scripts" / "agentbench" / "datasets" / "calibration-v1.json"
    )
    results = run_calibration(suite)
    assert len(results) >= 7
    assert all(result.calibrated for result in results)


def test_result_equivalence_accepts_order_alias_and_harmless_extra_column() -> None:
    generated = ResultTable(
        columns=("amount", "debug", "id"),
        rows=((20.0, "x", 2), (10, "y", 1)),
    )
    golden = ResultTable(columns=("id", "amount"), rows=((1, 10.0), (2, 20)))
    assert result_sets_equivalent(
        generated,
        golden,
        mode=ComparisonMode.EXACT,
        ordered=False,
        allow_extra_columns=True,
        absolute_tolerance=1e-9,
        relative_tolerance=1e-9,
    )


def test_result_equivalence_rejects_wrong_value() -> None:
    assert not result_sets_equivalent(
        ResultTable(columns=("total",), rows=((4,),)),
        ResultTable(columns=("total",), rows=((3,),)),
        mode=ComparisonMode.EXACT,
        ordered=False,
        allow_extra_columns=True,
        absolute_tolerance=1e-9,
        relative_tolerance=1e-9,
    )


def test_result_equivalence_accepts_same_projection_with_different_alias() -> None:
    assert result_sets_equivalent(
        ResultTable(columns=("order_count",), rows=((1000,),)),
        ResultTable(columns=("total",), rows=((1000,),)),
        mode=ComparisonMode.EXACT,
        ordered=False,
        allow_extra_columns=True,
        absolute_tolerance=1e-9,
        relative_tolerance=1e-9,
    )


def test_rejected_and_unknown_tools_count_as_failed_attempts() -> None:
    trace = TrialTrace(
        terminal_status="completed",
        answer="done",
        tools=(
            ToolTrace(name="update_plan", status="rejected"),
            ToolTrace(name="sql_validate", status="unknown"),
            ToolTrace(name="sql_execute_readonly", status="succeeded"),
        ),
    )

    assert failed_tool_call_ratio(trace) == pytest.approx(2 / 3)


def test_trace_contract_accepts_any_one_of_multiple_valid_tools() -> None:
    manifest = DatasetManifest.model_validate(
        {
            "schema_version": "1.0",
            "dataset_id": "alternative-tool-contract",
            "dataset_version": "1.0.0",
            "role": "regression",
            "seed_version": "seed-v1",
            "description": "alternative tool scoring contract",
            "cases": [
                {
                    "case_id": "alternative-tool-case",
                    "category": "recovery",
                    "capability": "bounded negative lookup",
                    "prompts": ["确认对象是否存在"],
                    "trace": {
                        "any_of_required_tools": [
                            ["schema_search", "schema_inspect"]
                        ],
                        "require_valid_citations": False,
                    },
                }
            ],
        }
    )
    case = manifest.cases[0]

    for tool_name in ("schema_search", "schema_inspect"):
        score = score_trial(
            case,
            TrialTrace(
                terminal_status="completed",
                answer="对象不存在。",
                tools=(ToolTrace(name=tool_name, status="succeeded"),),
            ),
        )
        assert score.passed

    score = score_trial(
        case,
        TrialTrace(terminal_status="completed", answer="对象不存在。"),
    )
    assert not score.passed
    assert "any_of_required_tools" in score.failed_checks


def test_continuity_trace_scores_every_run_and_duplicate_work() -> None:
    manifest = DatasetManifest.model_validate(
        {
            "schema_version": "1.0",
            "dataset_id": "continuity-trace-contract",
            "dataset_version": "1.0.0",
            "role": "regression",
            "seed_version": "seed-v1",
            "description": "continuity trace scoring contract",
            "cases": [
                {
                    "case_id": "continuity-trace-case",
                    "category": "continuity",
                    "capability": "multi-run completion without repeated work",
                    "prompts": ["first", "continue"],
                    "trace": {
                        "all_run_statuses": ["completed"],
                        "max_duplicate_tool_calls": 0,
                        "max_duplicate_query_fingerprints": 0,
                        "require_valid_citations": False,
                    },
                }
            ],
        }
    )
    case = manifest.cases[0]
    passing = TrialTrace(
        terminal_status="completed",
        run_statuses=("completed", "completed"),
        tools=(
            ToolTrace(name="sql_validate", status="succeeded", input_hash="a"),
            ToolTrace(name="sql_execute_readonly", status="succeeded", input_hash="b"),
        ),
        query_fingerprints=("query-a",),
        answer="完成。",
    )
    assert score_trial(case, passing).passed

    repeated = passing.model_copy(
        update={
            "run_statuses": ("failed", "completed"),
            "tools": (*passing.tools, passing.tools[0]),
            "query_fingerprints": ("query-a", "query-a"),
        }
    )
    score = score_trial(case, repeated)
    assert not score.passed
    assert {
        "all_run_statuses",
        "max_duplicate_tool_calls",
        "max_duplicate_query_fingerprints",
    } <= set(score.failed_checks)


def test_negative_lookup_accepts_one_expected_failed_attempt_as_evidence() -> None:
    manifest = DatasetManifest.model_validate(
        {
            "schema_version": "1.0",
            "dataset_id": "negative-evidence-contract",
            "dataset_version": "1.0.0",
            "role": "regression",
            "seed_version": "seed-v1",
            "description": "negative evidence scoring contract",
            "cases": [
                {
                    "case_id": "negative-evidence-case",
                    "category": "recovery",
                    "capability": "bounded negative lookup",
                    "prompts": ["确认对象不存在"],
                    "trace": {
                        "any_of_attempted_tools": [["schema_search", "schema_inspect"]],
                        "required_error_codes": ["SCHEMA_INSPECTION_FAILED"],
                        "require_valid_citations": False,
                    },
                }
            ],
        }
    )
    score = score_trial(
        manifest.cases[0],
        TrialTrace(
            terminal_status="completed",
            answer="对象不存在。",
            tools=(
                ToolTrace(
                    name="schema_inspect",
                    status="failed",
                    error_code="SCHEMA_INSPECTION_FAILED",
                ),
            ),
        ),
    )
    assert score.passed


def test_multi_prompt_limits_can_target_only_the_final_run() -> None:
    manifest = DatasetManifest.model_validate(
        {
            "schema_version": "1.0",
            "dataset_id": "final-run-resource-contract",
            "dataset_version": "1.0.0",
            "role": "regression",
            "seed_version": "seed-v1",
            "description": "separate scenario setup cost from continuation cost",
            "cases": [
                {
                    "case_id": "final-run-resource-case",
                    "category": "continuity",
                    "capability": "score continuation efficiency",
                    "prompts": ["准备结果", "继续"],
                    "trace": {
                        "max_tool_calls": 1,
                        "max_turns": 2,
                        "max_duplicate_tool_calls": 0,
                        "limit_scope": "final_run",
                        "require_valid_citations": False,
                    },
                    "budget": {
                        "max_tokens": 100,
                        "max_latency_ms": 100,
                        "scope": "final_run",
                    },
                }
            ],
        }
    )
    setup_tool = ToolTrace(
        name="schema_inspect",
        status="succeeded",
        input_hash="same",
    )
    continuation_tool = ToolTrace(
        name="result_inspect",
        status="succeeded",
        input_hash="result",
    )
    score = score_trial(
        manifest.cases[0],
        TrialTrace(
            terminal_status="completed",
            answer="完成。",
            tools=(setup_tool, setup_tool, continuation_tool),
            turn_count=7,
            token_count=900,
            latency_ms=900,
            run_statuses=("completed", "completed"),
            run_traces=(
                RunTrace(
                    status="completed",
                    tools=(setup_tool, setup_tool),
                    turn_count=5,
                    token_count=800,
                    latency_ms=800,
                ),
                RunTrace(
                    status="completed",
                    tools=(continuation_tool,),
                    turn_count=2,
                    token_count=100,
                    latency_ms=100,
                ),
            ),
        ),
    )
    assert score.passed


def test_generated_query_follows_first_answer_cited_result_artifact() -> None:
    artifacts = [
        SimpleNamespace(
            id="artifact_sql_main",
            type="sql",
            payload_json=json.dumps(
                {"safeSql": "SELECT main", "parameters": {"value": 1}}
            ),
        ),
        SimpleNamespace(
            id="artifact_result_main",
            type="result_view",
            payload_json=json.dumps(
                {"sourceSqlArtifactId": "artifact_sql_main"}
            ),
        ),
        SimpleNamespace(
            id="artifact_sql_check",
            type="sql",
            payload_json=json.dumps({"safeSql": "SELECT verification"}),
        ),
        SimpleNamespace(
            id="artifact_result_check",
            type="result_view",
            payload_json=json.dumps(
                {"sourceSqlArtifactId": "artifact_sql_check"}
            ),
        ),
    ]

    sql, parameters = _select_generated_query(
        artifacts,
        (
            "main {{cite:artifact_result_main}} "
            "check {{cite:artifact_result_check}}"
        ),
        json.loads,
        citation_references,
    )

    assert sql == "SELECT main"
    assert parameters == {"value": 1}


def test_statistical_summary_reports_tail_and_small_sample_uncertainty() -> None:
    values = distribution([10, 20, 30, 100])
    assert values["median"] == 25.0
    assert values["p90"] == pytest.approx(79.0)
    assert values["maximum"] == 100.0
    lower, upper = wilson_interval(10, 10)
    assert lower < 0.75
    assert upper == pytest.approx(1.0)


def test_plan_contract_requires_durable_updates_without_skipped_steps() -> None:
    manifest = DatasetManifest.model_validate(
        {
            "schema_version": "1.0",
            "dataset_id": "plan-contract",
            "dataset_version": "1.0.0",
            "role": "regression",
            "seed_version": "seed-v1",
            "description": "plan scoring contract",
            "cases": [
                {
                    "case_id": "plan-case",
                    "category": "planning",
                    "capability": "durable plan execution",
                    "prompts": ["完成多阶段分析"],
                    "trace": {"require_valid_citations": False},
                    "plan": {
                        "required": True,
                        "min_versions": 2,
                        "max_skipped_steps": 0,
                    },
                }
            ],
        }
    )
    case = manifest.cases[0]
    passed = score_trial(
        case,
        TrialTrace(
            terminal_status="completed",
            answer="分析完成。",
            plan=PlanTrace(
                exists=True,
                version_count=2,
                terminal_status="completed",
                step_count=2,
                completed_steps=2,
                stable_step_ids=True,
            ),
        ),
    )
    assert passed.passed

    failed = score_trial(
        case,
        TrialTrace(
            terminal_status="completed",
            answer="分析完成。",
            plan=PlanTrace(
                exists=True,
                version_count=1,
                terminal_status="completed",
                step_count=2,
                completed_steps=1,
                skipped_steps=1,
                stable_step_ids=False,
            ),
        ),
    )
    assert not failed.passed
    assert {
        "plan_min_versions",
        "plan_stable_step_ids",
        "plan_skipped_steps",
    } <= set(failed.failed_checks)


def test_duplicate_tool_ratio_uses_semantic_input_identity() -> None:
    trace = TrialTrace(
        terminal_status="completed",
        tools=(
            ToolTrace(name="schema_inspect", status="succeeded", input_hash="same"),
            ToolTrace(name="schema_inspect", status="failed", input_hash="same"),
            ToolTrace(name="schema_inspect", status="succeeded", input_hash="different"),
        ),
    )
    assert duplicate_tool_call_ratio(trace) == pytest.approx(1 / 3)


def test_real_provider_configuration_failures_are_unscored_infrastructure() -> None:
    assert (
        _infrastructure_reason("failed", "MODEL_PROVIDER_AUTHENTICATION_FAILED")
        == "MODEL_PROVIDER_AUTHENTICATION_FAILED"
    )
    assert _infrastructure_reason("failed", "MODEL_PROVIDER_RATE_LIMITED") == (
        "MODEL_PROVIDER_RATE_LIMITED"
    )
    assert _infrastructure_reason("failed", "MODEL_PROVIDER_REQUEST_REJECTED") is None
